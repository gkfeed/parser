from app.core.dispatcher import Dispatcher
from app.serializers.feed import Feed, Item


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
