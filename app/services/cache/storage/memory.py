from typing import Any

from ._base import BaseStorage as _BaseStorage


class MemoryStorage(_BaseStorage):
    def __init__(self) -> None:
        self.__storage = {}

    def get(self, id: str) -> Any:
        try:
            return self.__storage[id]
        except KeyError:
            raise ValueError('No such index: ' + id)

    def set(self, id: str, data: Any) -> None:
        self.__storage[id] = data
