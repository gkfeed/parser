import pytest
from app.parsers.tiktok import TikTokFeed
from . import fetch_items  # noqa

TIKTOK_FEED_DATA = {
    "type": "tiktok",
    "parser": TikTokFeed,
    "url": "https://www.tiktok.com/@sendependa_dio",
}


@pytest.mark.skip(reason="its not work")
@pytest.mark.parametrize("fetch_items", [TIKTOK_FEED_DATA], indirect=True)
async def test_tiktok_feed(fetch_items):  # noqa: F811
    assert len(await fetch_items) != 0
