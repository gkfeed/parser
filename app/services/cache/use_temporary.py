from typing import Any

from .storage.redis import RedisStorage
from .temporary import TemporaryCacheService


# NOTE: move to extensions
class UseTemporaryCacheServiceExtension[T = Any]:
    cache: TemporaryCacheService[T] = TemporaryCacheService(storage=RedisStorage())
