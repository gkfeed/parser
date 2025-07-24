from datetime import timedelta
from typing import Callable, Awaitable, Any, override

from app.serializers.feed import Item, Feed
from app.services.cache.temporary import (
    TemporaryCacheService,
)
from app.services.cache.storage.memory import MemoryStorage
from ._base import BaseMiddleware


class CacheMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self.__cache: TemporaryCacheService[list[Item]] = TemporaryCacheService(
            MemoryStorage()
        )

    @override
    async def __call__(
        self,
        parser: Callable[[Feed, dict[str, Any]], Awaitable[list[Item]]],
        feed: Feed,
        data: dict,
    ) -> list[Item]:
        cache_storage_time = timedelta(minutes=5)
        cache_storage_time_if_success = cache_storage_time
        if "cache_storage_time" in data:
            cache_storage_time = data["cache_storage_time"]
        if "cache_storage_time_if_success" in data:
            cache_storage_time_if_success = data["cache_storage_time_if_success"]

        cache_id = str(feed.id)
        if self.__cache.has_valid_cache(cache_id):
            return self.__cache.get(cache_id)

        items = await parser(feed, data)

        storage_time = cache_storage_time
        if len(items) > 0:
            storage_time = cache_storage_time_if_success

        self.__cache.set_with_expiry(cache_id, items, storage_time)

        return items
