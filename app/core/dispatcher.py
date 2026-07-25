import asyncio
import random
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from pydantic import TypeAdapter

from app.extensions.parsers.base import BaseFeed
from app.parsers import PARSERS
from app.serializers.feed import Feed, Item
from app.services.broker import BrokerError, BrokerService
from app.services.repositories.feed_parser import FeedParserRepository
from app.services.repositories.item_hash import ItemsHashRepository

from .storage import FeedStorage, ItemsStorage


class Dispatcher(ItemsStorage, FeedStorage):
    _failure_backoffs = (
        timedelta(minutes=15),
        timedelta(hours=1),
        timedelta(hours=6),
        timedelta(hours=24),
    )

    def __init__(
        self,
        broker: BrokerService,
        feed_parser_repository: type[FeedParserRepository] = FeedParserRepository,
        item_hash_repository: type[ItemsHashRepository] = ItemsHashRepository,
        parsers: Mapping[str, type[BaseFeed]] = PARSERS,
    ):
        self.broker = broker
        self.feed_parser_repository = feed_parser_repository
        self.item_hash_repository = item_hash_repository
        self.parsers = parsers
        self._failure_counts: dict[int, int] = {}

    async def dispatch(self):
        feeds = await self._get_all_feeds()
        async with asyncio.TaskGroup() as tg:
            for feed in feeds:
                if not await self._should_process_feed(feed):
                    continue

                tg.create_task(self._fetch_feed_items(feed))
                await asyncio.sleep(1)

    async def _should_process_feed(self, feed: Feed) -> bool:
        feed_parser = await self.feed_parser_repository.get_by_feed_id(feed.id)
        if not feed_parser:
            return True

        valid_for = feed_parser.valid_for
        if valid_for.tzinfo is None:
            valid_for = valid_for.replace(tzinfo=UTC)

        return valid_for < datetime.now(UTC)

    async def _fetch_feed_items(self, feed: Feed) -> None:
        parser_cls = self.parsers.get(feed.type)
        if not parser_cls:
            return

        try:
            items = await self._request_items_from_broker(feed)
        except BrokerError as e:
            print(f"Failed to process feed {feed.url}")
            print(e)
            await self._schedule_failure(feed.id)
            return

        self._failure_counts.pop(feed.id, None)

        if len(items) != 0:
            delta = getattr(
                parser_cls, "_cache_storage_time_if_success", timedelta(days=1)
            )
            items = await self._filter_seen_items(feed.id, items)
            await self._save_items(feed, items)
            print(f"Saved {len(items)} items for feed: {feed.url}")
        else:
            delta = getattr(parser_cls, "_cache_storage_time", timedelta(hours=1))

        new_valid_for = datetime.now(UTC) + delta
        await self.feed_parser_repository.upsert(feed.id, new_valid_for)

    async def _schedule_failure(self, feed_id: int) -> None:
        failure_count = self._failure_counts.get(feed_id, 0) + 1
        self._failure_counts[feed_id] = failure_count
        backoff = self._failure_backoffs[
            min(failure_count, len(self._failure_backoffs)) - 1
        ]
        jittered_backoff = backoff * random.uniform(0.9, 1.1)
        await self.feed_parser_repository.upsert(
            feed_id,
            datetime.now(UTC) + jittered_backoff,
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

    async def _filter_seen_items(self, feed_id: int, items: list[Item]) -> list[Item]:
        filtered_items = []
        for item in items:
            if not item.hash:
                print(f"warning: item has no hash, skipping seen check {item.link}")
                filtered_items.append(item)
                continue

            if await self.item_hash_repository.contains(item.hash, feed_id):
                continue

            await self.item_hash_repository.save(item.hash, feed_id)
            filtered_items.append(item)
        return filtered_items
