from typing import TypeVar
from datetime import datetime, timedelta

from . import CacheService

_T = TypeVar("_T")


class InvalidCache(Exception):
    """Cache by this id isn't accesseble"""


class TemporaryCacheService(CacheService[_T]):
    def set_with_expiry(self, id: str, data: _T, storage_time: timedelta) -> None:
        expire_at = (datetime.now() + storage_time).timestamp()
        self._storage.set(f"{id}__timestamp", expire_at)

        super().set(id, data)

    def get(self, id: str) -> _T:
        if not self.has_valid_cache(id):
            raise InvalidCache

        return super().get(id)

    def has_valid_cache(self, id: str) -> bool:
        try:
            expired_timestamp = self._storage.get(f"{id}__timestamp")
        except ValueError:
            return False

        return datetime.now().timestamp() < expired_timestamp
