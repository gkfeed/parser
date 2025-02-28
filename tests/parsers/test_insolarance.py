import pytest
from app.parsers.insolarance import InsolaranceFeed
from . import fetch_items  # noqa

INSOLARANCE_FEED_DATA = {
    "type": "insolarance",
    "parser": InsolaranceFeed,
    "url": "https://insolarance.com",
}


@pytest.mark.parametrize("fetch_items", [INSOLARANCE_FEED_DATA], indirect=True)
async def test_insolarance_feed(fetch_items):
    assert len(await fetch_items) != 0
