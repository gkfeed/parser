from typing import Any
import functools

from app.serializers.feed import Item, Feed
from app.parsers import FeedParser
from .log import LoggingMiddleware

_MIDDLEWARES = [LoggingMiddleware()]


async def wrap_middlewares(feed: Feed) -> list[Item]:
    async def parser_wrapper(feed: Feed, data: dict) -> Any:
        return await FeedParser(feed, data).parse()

    middleware = parser_wrapper
    for m in reversed(_MIDDLEWARES):
        middleware = functools.partial(m, middleware)

    return await middleware(feed, {})
