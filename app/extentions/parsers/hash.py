import json
from typing import override

from app.serializers.feed import Feed, Item
from app.services.hash import HashService
from .base import BaseFeed as _BaseFeed


class ItemsHashExtension(_BaseFeed):
    _should_hash_items = True

    @override
    def __init__(self, feed: Feed, data: dict) -> None:
        data["should_hash_items"] = self._should_hash_items
        data["hash_function"] = self._generate_hash
        super().__init__(feed, data)

    async def _generate_hash(self, item: Item) -> str:
        model_dict = item.json()
        data_str = json.dumps(model_dict, sort_keys=True)
        return HashService.hash_str(data_str)
