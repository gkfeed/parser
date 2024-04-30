from app.serializers.feed import Feed, Item
from app.services.repositories.item import ItemsRepository
from app.services.repositories.feed import FeedRepository


class ItemsStorage:
    @classmethod
    async def _save_items(cls, feed: Feed, items: list[Item]):
        await ItemsRepository(feed).add_items_to_feed(items)


class FeedStorage:
    @classmethod
    async def _get_all_feeds(cls) -> list[Feed]:
        return await FeedRepository.get_all()
