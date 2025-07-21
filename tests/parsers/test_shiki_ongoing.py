import pytest
from app.parsers.shiki_ongoing import ShikiOngoingFeed
from . import fetch_items  # noqa

SHIKI_ONGOING_FEED_DATA = {
    "type": "shiki:ongoing",
    "parser": ShikiOngoingFeed,
    "url": "https://shikimori.one/",
}


@pytest.mark.parametrize("fetch_items", [SHIKI_ONGOING_FEED_DATA], indirect=True)
async def test_shiki_ongoing_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) != 0
