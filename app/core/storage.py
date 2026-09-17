from app.serializers.feed import Feed, Item
from app.services.repositories.feed import FeedRepository
from app.services.repositories.item import ItemsRepository


class ItemsStorage:
    items_repository: ItemsRepository

    async def _save_items(self, feed: Feed, items: list[Item]) -> list[Item]:
        return await self.items_repository.add_items_to_feed(feed, items)


class FeedStorage:
    feed_repository: FeedRepository

    async def _get_all_feeds(self) -> list[Feed]:
        return await self.feed_repository.get_all()
