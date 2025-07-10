from datetime import timedelta
from typing import Callable, Awaitable, Any, override

from app.serializers.feed import Item, Feed
from app.services.cache.temporary import (
    TemporaryCacheService,
    ExpiredCache,
    UndefinedCache,
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
        try:
            items = self.__cache.get(cache_id)
        except (UndefinedCache, ExpiredCache):
            items = await parser(feed, data)
            if len(items) > 0:
                self.__cache.set_with_expiry(
                    cache_id, items, cache_storage_time_if_success
                )
            else:
                self.__cache.set_with_expiry(cache_id, items, cache_storage_time)

        return items
