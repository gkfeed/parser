from typing import TypeVar
from datetime import datetime, timedelta

from . import CacheService
from .storage import TStorage

_T = TypeVar('_T')


class ExpiredCache(Exception):
    """Cache has already expired"""


class UndefinedCache(Exception):
    """Cache by this id isn't accesseble"""


class TemporaryCacheService(CacheService[_T]):
    def __init__(self, storage: TStorage) -> None:
        super().__init__(storage)
        self.__timestamps_when_expired = {}

    def set(self, id: str, data: _T, storage_time: timedelta) -> None:
        self.__timestamps_when_expired[id] = (
            datetime.now() + storage_time
        ).timestamp()

        super().set(id, data)

    def get(self, id: str) -> _T:
        if self._is_cache_expired(id):
            raise ExpiredCache

        return super().get(id)

    def _is_cache_expired(self, id: str) -> bool:
        try:
            expired_timestamp = self.__timestamps_when_expired[id]
        except KeyError:
            raise UndefinedCache

        return datetime.now().timestamp() > expired_timestamp
