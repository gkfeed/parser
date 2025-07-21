import pytest
from bs4 import Tag
from app.parsers.x import XFeed
from app.serializers.feed import Feed


class MockedXFeed(XFeed):
    posts: list = []

    @property
    async def _posts(self) -> list[Tag]:
        self.posts = await super()._posts
        return self.posts


X_FEED_DATA = {"type": "x", "parser": MockedXFeed, "url": "https://x.com/tuckercarlson"}


@pytest.mark.skip(reason="its not work")
async def test_url_in_nitter():
    url = MockedXFeed(
        Feed(id=1, title="x", type="x", url=X_FEED_DATA["url"]), {}
    ).feed_url
    assert url.endswith("/tuckercarlson")


@pytest.mark.skip(reason="its not work")
@pytest.mark.parametrize("fetch_items", [X_FEED_DATA], indirect=True)
async def test_x_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) != 0
