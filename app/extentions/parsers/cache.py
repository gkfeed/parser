from datetime import timedelta

from app.services.cache.use_temporary import (
    UseTemporaryCacheServiceExtension,
    UndefinedCache,
    ExpiredCache,
)
from .base import BaseFeed as _BaseFeed


def async_store_in_cache_if_not_empty_for(storage_time: timedelta):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            cache = args[0].cache
            try:
                result = cache.get(args[0].feed.id)
            except (UndefinedCache, ExpiredCache):
                result = await func(*args, **kwargs)
                if result:
                    cache.set(args[0].feed.id, result, storage_time)
            return result

        return wrapper

    return decorator


class CacheFeedExtention(_BaseFeed, UseTemporaryCacheServiceExtension):
    pass
