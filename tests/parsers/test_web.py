import pytest
from app.parsers.web import WebFeed
from . import fetch_items  # noqa

WEB_FEED_DATA = {
    "type": "web",
    "parser": WebFeed,
    "url": "https://www.calnewport.com/feed/",
}


@pytest.mark.parametrize("fetch_items", [WEB_FEED_DATA], indirect=True)
async def test_web_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) != 0
