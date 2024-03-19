import functools
from typing import Callable, Awaitable, Any, Type

from app.serializers.feed import Feed, Item
from app.extentions.parsers.base import BaseFeed
from app.middlewares._base import BaseMiddleware


class MiddlewaresWrapper:
    _middlewares: list[BaseMiddleware] = []

    @classmethod
    def register_middleware(cls, middleware: BaseMiddleware):
        cls._middlewares.append(middleware)

    @classmethod
    def _wrap_middlewares(
        cls, parser: Type[BaseFeed]
    ) -> Callable[[Feed, dict[str, Any]], Awaitable[list[Item]]]:
        async def parser_wrapper(feed: Feed, data: dict) -> list[Item]:
            return await parser(feed, data).items

        middleware = parser_wrapper
        for m in reversed(cls._middlewares):
            middleware = functools.partial(m, middleware)

        return middleware
