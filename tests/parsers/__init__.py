import pytest

from app.core.dispatcher import Dispatcher
from app.serializers.feed import Feed, Item
import app.configs  # noqa


class MockedItemsStorage:
    def __init__(self):
        self.items = []

    async def _save_items(self, feed: Feed, items: list[Item]):
        if not items:
            return

        for i in items:
            self.items.append(i)


class FakeDispatcher(MockedItemsStorage, Dispatcher):
    def __init__(self):
        super().__init__()
        super(MockedItemsStorage, self).__init__()

    async def fetch_feed(self, feed: Feed):
        return await self._fetch_feed(feed)


@pytest.fixture
async def fetch_items(request):
    feed_data = getattr(request, "param", {})
    if feed_data:
        dp = FakeDispatcher()
        dp.register_parser(feed_data["type"], feed_data["parser"])

        feed = Feed(
            id=1, title=feed_data["type"], type=feed_data["type"], url=feed_data["url"]
        )

        await dp.fetch_feed(feed)
        return dp.items
    return []
