from .storage._base import BaseStorage


class CacheService[T]:
    def __init__(self, storage: BaseStorage) -> None:
        self._storage = storage

    def get(self, id: str) -> T:
        return self._storage.get(id)

    def set(self, id: str, data: T) -> None:
        self._storage.set(id, data)
