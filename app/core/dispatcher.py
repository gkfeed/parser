import asyncio
import random
from collections.abc import Collection, Mapping
from datetime import UTC, datetime, timedelta
from typing import Protocol

import structlog
from structlog.contextvars import bound_contextvars

from app.extensions.parsers.base import BaseFeed
from app.models.feed_parser import FeedParser
from app.parsers import PARSERS, ParserConfig
from app.serializers.feed import Feed, FeedResult, Item
from app.services.broker import (
    BrokerError,
    BrokerFeedUnavailable,
    BrokerNoWorker,
    BrokerService,
)

logger = structlog.get_logger(__name__)


class FeedParserRepositoryProtocol(Protocol):
    async def upsert(self, feed_id: int, next_run_at: datetime) -> FeedParser: ...


class FeedRepositoryProtocol(Protocol):
    async def get_eligible(self, parser_types: Collection[str]) -> list[Feed]: ...


class ItemsRepositoryProtocol(Protocol):
    async def add_items_to_feed(self, feed: Feed, items: list[Item]) -> list[Item]: ...


class Dispatcher:
    _failure_backoffs = (
        timedelta(minutes=15),
        timedelta(hours=1),
        timedelta(hours=6),
        timedelta(hours=24),
    )

    def __init__(
        self,
        broker: BrokerService,
        feed_parser_repository: FeedParserRepositoryProtocol,
        feed_repository: FeedRepositoryProtocol,
        items_repository: ItemsRepositoryProtocol,
        parsers: Mapping[str, type[BaseFeed]] = PARSERS,
        broker_wait_timeout: int = 300,
    ):
        self.broker = broker
        self.feed_parser_repository = feed_parser_repository
        self.feed_repository = feed_repository
        self.items_repository = items_repository
        self.parsers = parsers
        self.broker_wait_timeout = broker_wait_timeout
        self._failure_counts: dict[int, int] = {}

    async def dispatch(self):
        feeds = await self.feed_repository.get_eligible(self.parsers.keys())
        async with asyncio.TaskGroup() as tg:
            for feed in feeds:
                tg.create_task(self._fetch_feed_items(feed))
                await asyncio.sleep(1)

    async def _fetch_feed_items(self, feed: Feed) -> None:
        with bound_contextvars(feed_id=feed.id, parser=feed.type):
            await self._fetch_feed_items_with_context(feed)

    async def _fetch_feed_items_with_context(self, feed: Feed) -> None:
        parser_cls = self.parsers.get(feed.type)
        if not parser_cls:
            return

        try:
            result = await self._request_items_from_broker(feed)
        except BrokerNoWorker as exc:
            next_retry = datetime.now(UTC) + timedelta(minutes=1)
            await self.feed_parser_repository.upsert(feed.id, next_retry)
            logger.warning(
                "feed_broker_wait_deadline",
                feed_id=feed.id,
                broker_task_id=exc.task_id,
                claim_state="pending",
                recovery_action="reuse_task_on_retry",
                next_retry=next_retry.isoformat(),
            )
            return
        except BrokerFeedUnavailable as exc:
            logger.warning("feed_unavailable", reason=exc.reason)
            if exc.retry_at is None:
                await self._schedule_failure(feed.id)
                return
            next_retry = max(exc.retry_at, datetime.now(UTC) + timedelta(seconds=1))
            await self.feed_parser_repository.upsert(feed.id, next_retry)
            logger.info(
                "feed_retry_scheduled",
                reason=exc.reason,
                next_retry=next_retry.isoformat(),
            )
            return
        except BrokerError:
            logger.exception("feed_dispatch_failed")
            await self._schedule_failure(feed.id)
            return

        self._failure_counts.pop(feed.id, None)
        items = result.items
        received = len(items)
        policy = ParserConfig(feed.type, parser_cls).scheduling_policy
        delta = policy.delay_for_result(has_items=bool(items))

        if items:
            items = await self.items_repository.add_items_to_feed(feed, items)

        now = datetime.now(UTC)
        if result.retry_at is None:
            next_run_at = now + delta
        else:
            next_run_at = max(result.retry_at, now + timedelta(seconds=1))
            logger.info(
                "feed_retry_scheduled",
                reason="parser_requested_retry",
                next_retry=next_run_at.isoformat(),
            )
        await self.feed_parser_repository.upsert(feed.id, next_run_at)
        logger.info("feed_items_received", received=received, returned=len(items))

    async def _schedule_failure(self, feed_id: int) -> None:
        failure_count = self._failure_counts.get(feed_id, 0) + 1
        self._failure_counts[feed_id] = failure_count
        backoff = self._failure_backoffs[
            min(failure_count, len(self._failure_backoffs)) - 1
        ]
        jittered_backoff = backoff * random.uniform(0.9, 1.1)
        next_retry = datetime.now(UTC) + jittered_backoff
        await self.feed_parser_repository.upsert(feed_id, next_retry)
        logger.warning(
            "feed_retry_scheduled",
            failure_count=failure_count,
            next_retry=next_retry.isoformat(),
        )

    async def _request_items_from_broker(self, feed: Feed) -> FeedResult:
        items_json = await self.broker.put_and_wait_for_result(
            f"gkfeed.process_feed_{feed.type}",
            (feed.model_dump_json(),),
            timeout=self.broker_wait_timeout,
            task_key=f"feed:{feed.id}",
        )

        return FeedResult.model_validate_json(items_json)
