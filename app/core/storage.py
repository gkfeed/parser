from app.serializers.feed import Feed, Item
from app.services.repositories.item import ItemsRepository
from app.services.repositories.feed import FeedRepository


class ItemsStorage:
    async def _save_items(self, feed: Feed, items: list[Item]):
        await ItemsRepository(feed).add_items_to_feed(items)


class FeedStorage:
    async def _get_all_feeds(self) -> list[Feed]:
        return await FeedRepository.get_all()
