from typing import Generic, TypeVar

from .storage import TStorage


_T = TypeVar('_T')


class _CacheServiceMixin(Generic[_T]):
    pass


class CacheService(_CacheServiceMixin[_T]):
    def __init__(self, storage: TStorage) -> None:
        self._storage = storage

    def get(self, id: str) -> _T:
        return self._storage.get(id)

    def set(self, id: str, data: _T) -> None:
        self._storage.set(id, data)
