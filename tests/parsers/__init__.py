import json
from collections.abc import Callable
from hashlib import sha256
from typing import TypedDict, cast

import pytest

from app.core.parsers import FeedParsingContext
from app.extensions.parsers.base import BaseFeed
from app.extensions.parsers.hash import ItemsHashExtension
from app.serializers.feed import Feed, Item


class FeedData(TypedDict):
    type: str
    parser: type[BaseFeed]
    url: str


class MockedItemsStorage:
    def __init__(self):
        self.items = []

    async def _save_items(self, feed: Feed, items: list[Item]):
        if not items:
            return

        for i in items:
            self.items.append(i)


class FakeDispatcher(MockedItemsStorage, FeedParsingContext):
    def __init__(self):
        super().__init__()
        FeedParsingContext.__init__(self)

    async def fetch_feed(self, feed: Feed):
        if feed.type not in self._parsers:
            return

        parser = self._parsers[feed.type](feed, self.get_parser_initial_data(feed))
        items = await parser.items
        if isinstance(parser, ItemsHashExtension):
            items = await parser.apply_hashes(items)
        await self._save_items(feed, items)


def check_item_hashes(cache: pytest.Cache, feed: Feed, items: list[Item]) -> None:
    feed_key = sha256(json.dumps([feed.type, feed.url]).encode()).hexdigest()
    cache_key = f"parser_item_hashes/v1/{feed_key}"
    snapshots = [item.model_dump(mode="json") for item in items]
    cache.set(f"{cache_key}/latest", {"feed": feed.model_dump(), "items": snapshots})

    hashes = [item.hash for item in items if item.hash is not None]
    assert len(hashes) == len(items), f"Missing hashes for {feed.url}"
    assert len(hashes) == len(set(hashes)), f"Duplicate item hashes for {feed.url}"

    history = cache.get(f"{cache_key}/history", {})
    for item, snapshot in zip(items, snapshots, strict=True):
        identity = json.dumps([item.title, item.link, item.text])
        previous = history.get(identity)
        assert previous is None or previous["hash"] == item.hash, (
            f"Item hash changed for {feed.url}: {previous!r} -> {snapshot!r}"
        )
        history.setdefault(identity, snapshot)

    cache.set(f"{cache_key}/history", history)


@pytest.fixture
async def fetch_items(request, cache: pytest.Cache):
    raw_feed_data = getattr(request, "param", None)
    feed_data: FeedData | None = None
    if isinstance(raw_feed_data, dict):
        feed_data = cast("FeedData", raw_feed_data)
    elif raw_feed_data is not None:
        factory = cast("Callable[[], FeedData]", raw_feed_data)
        feed_data = factory()

    if feed_data is not None:
        dp = FakeDispatcher()
        dp.register_parser(feed_data["type"], feed_data["parser"])

        feed = Feed(
            id=1, title=feed_data["type"], type=feed_data["type"], url=feed_data["url"]
        )

        await dp.fetch_feed(feed)
        check_item_hashes(cache, feed, dp.items)
        return dp.items
    return []
