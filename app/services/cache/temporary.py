from typing import TypeVar
from datetime import datetime, timedelta

from . import CacheService
from .storage._base import BaseStorage

_T = TypeVar("_T")


class InvalidCache(Exception):
    """Cache by this id isn't accesseble"""


class TemporaryCacheService(CacheService[_T]):
    def __init__(self, storage: BaseStorage) -> None:
        super().__init__(storage)
        self.__timestamps_when_expired: dict[str, float] = {}

    def set_with_expiry(self, id: str, data: _T, storage_time: timedelta) -> None:
        self.__timestamps_when_expired[id] = (datetime.now() + storage_time).timestamp()

        super().set(id, data)

    def get(self, id: str) -> _T:
        if not self.has_valid_cache(id):
            raise InvalidCache

        return super().get(id)

    def has_valid_cache(self, id: str) -> bool:
        if id not in self.__timestamps_when_expired:
            return False

        expired_timestamp = self.__timestamps_when_expired[id]
        return datetime.now().timestamp() < expired_timestamp
