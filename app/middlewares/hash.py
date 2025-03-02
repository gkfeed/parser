from typing import Callable, Awaitable, Any, override

from app.serializers.feed import Item, Feed
from app.services.repositories.item_hash import ItemsHashRepository
from ._base import BaseMiddleware


class HashMiddleware(BaseMiddleware):
    @override
    async def __call__(
        self,
        parser: Callable[[Feed, dict[str, Any]], Awaitable[list[Item]]],
        feed: Feed,
        data: dict,
    ) -> list[Item]:
        items = await parser(feed, data)
        if "should_hash_items" not in data:
            return items

        hash_function = data["hash_function"]
        items_to_remove = []
        for item in items:
            hash = await hash_function(item)
            if await ItemsHashRepository.contains(hash):
                items_to_remove.append(item)
            else:
                await ItemsHashRepository.save(hash)

        print(f"{feed.url}: -{len(items_to_remove)} hashed")
        return [item for item in items if item not in items_to_remove]
