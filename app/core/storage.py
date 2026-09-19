from collections.abc import Collection

from app.serializers.feed import Feed, Item
from app.services.repositories.feed import FeedRepository
from app.services.repositories.item import ItemsRepository


class ItemsStorage:
    async def _save_items(self, feed: Feed, items: list[Item]) -> list[Item]:
        return await ItemsRepository.add_items_to_feed(feed, items)


class FeedStorage:
    async def _get_eligible_feeds(self, parser_types: Collection[str]) -> list[Feed]:
        return await FeedRepository.get_eligible(parser_types)
