import pytest
from app.parsers.shiki import ShikiFeed
from . import fetch_items  # noqa

SHIKI_FEED_DATA = {
    "type": "shiki",
    "parser": ShikiFeed,
    "url": "https://shikimori.one/animes/51180",
}


@pytest.mark.parametrize("fetch_items", [SHIKI_FEED_DATA], indirect=True)
async def test_shiki_feed(fetch_items):
    assert len(await fetch_items) != 0
