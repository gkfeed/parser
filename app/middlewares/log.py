from typing import Callable, Awaitable, Any, override

from app.serializers.feed import Item, Feed
from ._base import BaseMiddleware


class LoggingMiddleware(BaseMiddleware):
    @override
    async def __call__(
        self,
        parser: Callable[[Feed, dict[str, Any]], Awaitable[list[Item]]],
        feed: Feed,
        data: dict,
    ) -> list[Item]:
        items = await parser(feed, data)
        print(feed.url, ":", len(items))
        return items
