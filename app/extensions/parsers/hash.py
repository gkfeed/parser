import json
from typing import override

from app.serializers.feed import Item
from app.services.hash import HashService

from .base import BaseFeed as _BaseFeed


class ItemsHashExtension(_BaseFeed):
    async def _generate_hash(self, item: Item) -> str:
        model_dict = item.model_dump()
        data_str = json.dumps(model_dict, sort_keys=True, default=str)
        return HashService.hash_str(data_str)

    async def apply_hashes(self, items: list[Item]) -> list[Item]:
        for item in items:
            if item.hash is None:
                item.hash = await self._generate_hash(item)
        return items


class ItemLinkHashExtension(ItemsHashExtension):
    """Hash the item link without normalization or other item fields."""

    @override
    async def _generate_hash(self, item: Item) -> str:
        return HashService.hash_str(item.link)


class ItemIdentityHashExtension(ItemsHashExtension):
    """Hash the title/link/text identity used by repository fallback deduplication."""

    @override
    async def _generate_hash(self, item: Item) -> str:
        identity = json.dumps([item.title, item.link, item.text])
        return HashService.hash_str(identity)
