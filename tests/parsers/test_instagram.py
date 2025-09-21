import pytest
from app.parsers.instagram import InstagramFeed
from . import fetch_items  # noqa

INSTAGRAM_FEED_DATA = {
    "type": "inst",
    "parser": InstagramFeed,
    "url": "https://www.instagram.com/makaryshaa",
}


@pytest.mark.parametrize("fetch_items", [INSTAGRAM_FEED_DATA], indirect=True)
async def test_instagram_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) != 0
    for item in fetch_items:
        assert item.link.startswith("http")
