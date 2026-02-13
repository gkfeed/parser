import asyncio
from datetime import datetime, timezone, timedelta

from pydantic import TypeAdapter

from app.services.broker import BrokerService, BrokerError
from app.serializers.feed import Item, Feed
from app.services.repositories.feed_parser import FeedParserRepository
from app.services.repositories.item_hash import ItemsHashRepository
from app.parsers import PARSERS
from .storage import ItemsStorage, FeedStorage


class Dispatcher(ItemsStorage, FeedStorage):
    def __init__(self, broker_url: str):
        self.broker = BrokerService(broker_url)

    async def dispatch(self):
        feeds = await self._get_all_feeds()
        async with asyncio.TaskGroup() as tg:
            for feed in feeds:
                if not await self._should_process_feed(feed):
                    continue

                tg.create_task(self._fetch_feed_items(feed))
                await asyncio.sleep(1)

    async def _should_process_feed(self, feed: Feed) -> bool:
        feed_parser = await FeedParserRepository.get_by_feed_id(feed.id)
        if not feed_parser:
            return True

        valid_for = feed_parser.valid_for
        if valid_for.tzinfo is None:
            valid_for = valid_for.replace(tzinfo=timezone.utc)

        return valid_for < datetime.now(timezone.utc)

    async def _fetch_feed_items(self, feed: Feed) -> None:
        parser_cls = PARSERS.get(feed.type)
        if not parser_cls:
            return

        try:
            items_json = await self.broker.put_and_wait_for_result(
                f"gkfeed.process_feed_{feed.type}",
                (feed.model_dump_json(),),
                timeout=300,
            )
        except BrokerError as e:
            print(f"Failed to process feed {feed.url}")
            print(e)
            delta = getattr(parser_cls, "_cache_storage_time", timedelta(hours=1))
            new_valid_for = datetime.now(timezone.utc) + delta
            return

        adapter = TypeAdapter(list[Item])
        items = adapter.validate_json(items_json)

        items = await self._filter_seen_items(feed.id, items)

        await self._save_items(feed, items)
        print(f"Saved {len(items)} items for feed: {feed.url}")

        delta = getattr(parser_cls, "_cache_storage_time_if_success", timedelta(days=1))

        new_valid_for = datetime.now(timezone.utc) + delta
        await FeedParserRepository.upsert(feed.id, new_valid_for)

    @staticmethod
    async def _filter_seen_items(feed_id: int, items: list[Item]) -> list[Item]:
        filtered_items = []
        for item in items:
            if item.hash:
                if not await ItemsHashRepository.contains(item.hash, feed_id):
                    await ItemsHashRepository.save(item.hash, feed_id)
                    filtered_items.append(item)
            else:
                filtered_items.append(item)
        return filtered_items
