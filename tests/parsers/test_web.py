import pytest
from app.parsers.web import WebFeed
from . import fetch_items  # noqa

WEB_FEED_DATA = {
    "type": "web",
    "parser": WebFeed,
    "url": "https://beardycast.com/feed/",
}


@pytest.mark.parametrize("fetch_items", [WEB_FEED_DATA], indirect=True)
async def test_web_feed(fetch_items):
    assert len(await fetch_items) != 0
