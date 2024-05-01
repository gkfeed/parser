import functools
from typing import Callable, Awaitable, Any

from app.serializers.feed import Feed, Item
from app.middlewares._base import BaseMiddleware

_PARSER_TYPE = Callable[[Feed, dict[str, Any]], Awaitable[list[Item]]]


class MiddlewaresWrapper:
    def __init__(self):
        self._middlewares: list[BaseMiddleware] = []

    def register_middleware(self, middleware: BaseMiddleware):
        self._middlewares.append(middleware)

    def _wrap_middlewares(self, parser: _PARSER_TYPE) -> _PARSER_TYPE:
        async def parser_wrapper(feed: Feed, data: dict) -> list[Item]:
            return await parser(feed, data)

        middleware = parser_wrapper
        for m in reversed(self._middlewares):
            middleware = functools.partial(m, middleware)

        return middleware
