from typing import Callable, Awaitable, Any

from app.serializers.feed import Feed, Item
from app.middlewares._base import BaseMiddleware
from app.extentions.parsers.base import BaseFeed
from ..parsers import FakeDispatcher


class FakeFeed(BaseFeed):
    def __init__(self, feed: Feed, data: dict) -> None:
        super().__init__(feed, data)
        self.data["test"] = "1"

    # TODO: somehow write data init here
    # def __init_subclass__(cls) -> None:
    #     pass


class FakeMiddleware(BaseMiddleware):
    async def __call__(
        self,
        parser: Callable[[Feed, dict[str, Any]], Awaitable[list[Item]]],
        feed: Feed,
        data: dict,
    ) -> list[Item]:
        assert data["test"] == "1"
        items = await parser(feed, data)
        "after"
        return items


def test_if_initial_data_in_storage():
    feed = Feed(id=1, type="type", title="title", url="url")
    data = FakeFeed(feed, {}).data
    assert data["test"] == "1"


async def test_if_initial_parser_data_is_usefull():
    dp = FakeDispatcher()
    feed = Feed(id=1, type="type", title="title", url="url")

    dp.register_middleware(FakeMiddleware())
    dp.register_parser("type", FakeFeed)

    await dp.fetch_feed(feed)
