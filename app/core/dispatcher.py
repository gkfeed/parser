import asyncio
import random
from collections.abc import Collection, Mapping
from datetime import UTC, datetime, timedelta
from typing import Protocol

import structlog
from pydantic import TypeAdapter
from structlog.contextvars import bound_contextvars

from app.extensions.parsers.base import BaseFeed
from app.models.feed_parser import FeedParser
from app.parsers import PARSERS
from app.serializers.feed import Feed, Item
from app.services.broker import BrokerError, BrokerService
from app.services.repositories.feed import FeedRepository
from app.services.repositories.feed_parser import FeedParserRepository
from app.services.repositories.item import ItemsRepository

logger = structlog.get_logger(__name__)


class FeedParserRepositoryProtocol(Protocol):
    async def upsert(self, feed_id: int, valid_for: datetime) -> FeedParser: ...


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
        feed_parser_repository: FeedParserRepositoryProtocol = FeedParserRepository,
        parsers: Mapping[str, type[BaseFeed]] = PARSERS,
        feed_repository: FeedRepositoryProtocol = FeedRepository,
        items_repository: ItemsRepositoryProtocol = ItemsRepository,
    ):
        self.broker = broker
        self.feed_parser_repository = feed_parser_repository
        self.feed_repository = feed_repository
        self.items_repository = items_repository
        self.parsers = parsers
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
            items = await self._request_items_from_broker(feed)
        except BrokerError:
            logger.exception("feed_dispatch_failed")
            await self._schedule_failure(feed.id)
            return

        self._failure_counts.pop(feed.id, None)
        received = len(items)

        if len(items) != 0:
            delta = getattr(
                parser_cls, "_cache_storage_time_if_success", timedelta(days=1)
            )
            items = await self._save_items(feed, items)
        else:
            delta = getattr(parser_cls, "_cache_storage_time", timedelta(hours=1))

        new_valid_for = datetime.now(UTC) + delta
        await self.feed_parser_repository.upsert(feed.id, new_valid_for)
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

    async def _request_items_from_broker(self, feed: Feed) -> list[Item]:
        items_json = await self.broker.put_and_wait_for_result(
            f"gkfeed.process_feed_{feed.type}",
            (feed.model_dump_json(),),
            timeout=300,
        )

        adapter = TypeAdapter(list[Item])
        items = adapter.validate_json(items_json)

        return items

    async def _save_items(self, feed: Feed, items: list[Item]) -> list[Item]:
        return await self.items_repository.add_items_to_feed(feed, items)
