import pytest
from app.parsers.ranobeme import RanobeMeFeed
from . import fetch_items  # noqa

RANOBEME_FEED_DATA = {
    "type": "ranobeme",
    "parser": RanobeMeFeed,
    "url": "https://ranobe.me/ranobe166",
}


@pytest.mark.parametrize("fetch_items", [RANOBEME_FEED_DATA], indirect=True)
async def test_ranobeme_feed(fetch_items):
    assert len(await fetch_items) != 0
