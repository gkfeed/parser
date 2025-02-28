import pytest
from app.parsers.rezka import RezkaFeed
from . import fetch_items  # noqa

REZKA_FEED_DATA = {
    "type": "rezka",
    "parser": RezkaFeed,
    "url": "https://hdrezka.me/series/drama/63941-slovo-pacana-krov-na-asfalte-2023.html",
}


@pytest.mark.parametrize("fetch_items", [REZKA_FEED_DATA], indirect=True)
async def test_rezka_feed(fetch_items):
    assert len(await fetch_items) != 0
