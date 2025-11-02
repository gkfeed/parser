import pytest

from app.parsers.liquidpedia import LiquidpediaFeed
from . import fetch_items  # noqa

LIQUIDPEDIA_FEED_DATA = {
    "type": "liquidpedia",
    "parser": LiquidpediaFeed,
    "url": "https://liquipedia.net/dota2/Team_Spirit",
}


@pytest.mark.parametrize("fetch_items", [LIQUIDPEDIA_FEED_DATA], indirect=True)
async def test_liquidpedia_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) != 0
