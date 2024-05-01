from bs4 import Tag

from app.serializers.feed import Feed
from app.parsers.x import XFeed
from . import FakeDispatcher

feed = Feed(
    id=1,
    title="x",
    type="x",
    url="https://x.com/tuckercarlson",
)


class MockedXFeed(XFeed):
    posts: list = []

    @property
    async def _posts(self) -> list[Tag]:
        self.posts = await super()._posts
        return self.posts


async def test_url_in_nitter():
    url = MockedXFeed(feed, {}).feed_url

    assert url.endswith("/tuckercarlson")


async def test_posts_extract():
    parser = MockedXFeed(feed, {})
    await parser.items

    assert len(parser.posts) != 0


async def test_x_feed():
    dp = FakeDispatcher()

    dp.register_parser("x", MockedXFeed)
    await dp.fetch_feed(feed)

    # test if parser actually works
    assert len(dp.items) != 0
