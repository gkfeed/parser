import pytest

from app.core.parsers import FeedParsingContext
from app.serializers.feed import Feed, Item


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

        items = await self.execute_parser(feed, self.get_parser_initial_data(feed))
        await self._save_items(feed, items)


@pytest.fixture
async def fetch_items(request):
    feed_data = getattr(request, "param", {})
    if callable(feed_data):
        feed_data = feed_data()
    if feed_data:
        dp = FakeDispatcher()
        dp.register_parser(feed_data["type"], feed_data["parser"])

        feed = Feed(
            id=1, title=feed_data["type"], type=feed_data["type"], url=feed_data["url"]
        )

        await dp.fetch_feed(feed)
        return dp.items
    return []
