from abc import abstractmethod
from collections.abc import Mapping
from datetime import datetime
from typing import final

from structlog.contextvars import bound_contextvars

from app.core.worker_kind import WorkerKind
from app.serializers.feed import Feed, Item


class BaseFeed:
    worker_kind = WorkerKind.HTTP

    def __init__(self, feed: Feed, data: Mapping[str, object] | None = None) -> None:
        # Empty dictionaries remain accepted while existing integration callers
        # migrate to the feed-only constructor. There is no generic data channel.
        if data:
            raise ValueError("Parser data is no longer supported; use typed fields")
        self.feed = feed
        self.retry_at: datetime | None = None

    @property
    @final
    async def items(self) -> list[Item]:
        with bound_contextvars(feed_id=self.feed.id, parser=self.feed.type):
            return await self._parse_items()

    @abstractmethod
    async def _parse_items(self) -> list[Item]:
        pass
