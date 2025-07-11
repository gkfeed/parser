from typing import TypeVar, Generic
from datetime import timedelta
from .storage.memory import MemoryStorage
from .temporary import TemporaryCacheService

_T = TypeVar("_T")


# NOTE: move to extensions
class UseTemporaryCacheServiceExtension(Generic[_T]):
    cache: TemporaryCacheService[_T] = TemporaryCacheService(storage=MemoryStorage())


def async_store_in_cache_for(storage_time: timedelta):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            cache = args[0].cache

            if cache.has_valid_cache(args[1]):
                return cache.get(args[1])

            result = await func(*args, **kwargs)
            cache.set_with_expiry(args[1], result, storage_time)
            return result

        return wrapper

    return decorator
