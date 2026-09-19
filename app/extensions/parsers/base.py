from abc import abstractmethod
from typing import final

from structlog.contextvars import bound_contextvars

from app.core.worker_kind import WorkerKind
from app.serializers.feed import Feed, Item


class BaseFeed:
    worker_kind = WorkerKind.HEAVY

    def __init__(self, feed: Feed, data: dict) -> None:
        self.feed = feed
        self.data = data

    @property
    @final
    async def items(self) -> list[Item]:
        with bound_contextvars(feed_id=self.feed.id, parser=self.feed.type):
            return await self._parse_items()

    @abstractmethod
    async def _parse_items(self) -> list[Item]:
        pass
