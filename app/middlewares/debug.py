from typing import Callable, Awaitable, Any, override
import sys

from app.extensions.parsers.exceptions import UnavailableFeed
from app.serializers.feed import Item, Feed
from ._base import BaseMiddleware


class DebugFeedMiddleware(BaseMiddleware):
    def __init__(self, print_traceback: bool = False):
        self.print_traceback = print_traceback

    @override
    async def __call__(
        self,
        parser: Callable[[Feed, dict[str, Any]], Awaitable[list[Item]]],
        feed: Feed,
        data: dict,
    ) -> list[Item]:
        try:
            items = await parser(feed, data)
        except Exception as e:
            if e is not UnavailableFeed or self.print_traceback:
                exc_type, exc_value, tb = sys.exc_info()
                import pdb

                pdb.post_mortem(tb)

            items = []

        return items
