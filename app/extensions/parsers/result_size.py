from abc import abstractmethod

from app.serializers.feed import Item

from .base import BaseFeed as _BaseFeed


class ResultSizeExtension(_BaseFeed):
    @abstractmethod
    async def reduce_result_size(
        self, original_items: list[Item], attempt: int
    ) -> list[Item] | None:
        """Prepare a smaller result after the broker rejects it with HTTP 413."""
