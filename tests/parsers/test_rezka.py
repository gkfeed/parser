import pytest
from app.parsers.rezka import RezkaFeed, RezkaCollecionFeed
from . import fetch_items  # noqa

REZKA_FEED_DATA = [
    {
        "type": "rezka",
        "parser": RezkaFeed,
        "url": "https://hdrezka.me/series/drama/63941-slovo-pacana-krov-na-asfalte-2023.html",
    },
    {
        "type": "rezka:collection",
        "parser": RezkaCollecionFeed,
        "url": "https://hdrezka.me/collections/319-serialy-tnt/?filter=last",
    },
    {
        "type": "rezka:collection",
        "parser": RezkaCollecionFeed,
        "url": "https://hdrezka.me/?filter=watching",
    },
]


@pytest.mark.parametrize("fetch_items", REZKA_FEED_DATA, indirect=True)
async def test_rezka_feed(fetch_items):
    assert len(await fetch_items) != 0
