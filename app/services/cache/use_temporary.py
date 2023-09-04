from typing import TypeVar, Generic
from datetime import timedelta
from .storage.memory import MemoryStorage
from .temporary import TemporaryCacheService, UndefinedCache, ExpiredCache

_T = TypeVar('_T')


class _UseTemporaryCacheServiceMixin(Generic[_T]):
    pass


class UseTemporaryCacheServiceExtension(Generic[_T]):
    cache: TemporaryCacheService[_T] = TemporaryCacheService(
        storage=MemoryStorage()
    )


def async_store_in_cache_for(storage_time: timedelta):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            cache = args[0].cache
            try:
                result = cache.get(args[1])
            except (UndefinedCache, ExpiredCache):
                result = await func(*args, **kwargs)
                cache.set(args[1], result, storage_time)
            return result
        return wrapper
    return decorator
