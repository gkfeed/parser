import pytest
from app.parsers.mangalib import MangaLibFeed
from . import fetch_items  # noqa

MANGALIB_FEED_DATA = {
    "type": "mangalib",
    "parser": MangaLibFeed,
    "url": "https://mangalib.org/ru/manga/4731--yuukoku-no-moriarty",
}


@pytest.mark.parametrize("fetch_items", [MANGALIB_FEED_DATA], indirect=True)
async def test_mangalib_feed(fetch_items):  # noqa: F811
    assert len(await fetch_items) != 0
