import pytest
from app.parsers.rezka import RezkaFeed, RezkaCollectionFeed
from . import fetch_items  # noqa

REZKA_FEED_DATA = [
    {
        "type": "rezka",
        "parser": RezkaFeed,
        "url": "https://hdrezka.me/series/drama/63941-slovo-pacana-krov-na-asfalte-2023.html",
    },
    {
        "type": "rezka",
        "parser": RezkaFeed,
        "url": "https://hdrezka.me/series/thriller/41647-igra-v-kalmara-2021-latest.html",
    },
    {
        "type": "rezka:collection",
        "parser": RezkaCollectionFeed,
        "url": "https://hdrezka.me/collections/319-serialy-tnt/?filter=last",
    },
    {
        "type": "rezka:collection",
        "parser": RezkaCollectionFeed,
        "url": "https://hdrezka.me/?filter=watching",
    },
]


@pytest.mark.parametrize("fetch_items", REZKA_FEED_DATA, indirect=True)
async def test_rezka_feed(fetch_items):  # noqa: F811
    assert len(await fetch_items) != 0
