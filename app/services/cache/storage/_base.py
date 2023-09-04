from abc import ABC, abstractmethod
from typing import Any


class BaseStorage(ABC):
    @abstractmethod
    def get(self, id: str) -> Any:
        pass

    @abstractmethod
    def set(self, id: str, data: Any) -> None:
        pass
