import pytest
from app.parsers.yummyanime import YummyAnimeFeed
from . import fetch_items  # noqa

YUMMYANIME_FEED_DATA = {
    "type": "yummyanime",
    "parser": YummyAnimeFeed,
    "url": "https://yummyanime.org/4723-.html",
}


@pytest.mark.parametrize("fetch_items", [YUMMYANIME_FEED_DATA], indirect=True)
async def test_yummyanime_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) != 0
