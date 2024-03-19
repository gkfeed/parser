from app.serializers.feed import Feed, Item
from app.services.repositories.item import ItemsRepository


class ItemsStorage:
    @classmethod
    async def _save_items(cls, feed: Feed, items: list[Item]):
        await ItemsRepository(feed).add_items_to_feed(items)
