from abc import ABC, abstractmethod
from typing import Callable, Awaitable, Any

from app.serializers.feed import Item, Feed


class BaseMiddleware(ABC):
    @abstractmethod
    async def __call__(
        self,
        parser: Callable[[Feed, dict[str, Any]], Awaitable[list[Item]]],
        feed: Feed,
        data: dict,
    ) -> list[Item]:
        "before"
        items = await parser(feed, data)
        "after"
        return items
