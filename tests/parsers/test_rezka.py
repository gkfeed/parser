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
        "type": "rezka",
        "parser": RezkaFeed,
        "url": "https://hdrezka.me/films/action/64700-major-grom-game-the-2024.html",
    },
    {
        "type": "rezka",
        "parser": RezkaFeed,
        "url": "https://hdrezka.me/series/comedy/78072-univer-molodye-2025.html",
    },
    {
        "type": "rezka",
        "parser": RezkaFeed,
        "url": "https://hdrezka.me/series/comedy/78836-pozhit-kak-lyudi-2025.html",
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


# @pytest.mark.skip(reason="tmp unavailable")
@pytest.mark.parametrize("fetch_items", REZKA_FEED_DATA, indirect=True)
async def test_rezka_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) != 0


@pytest.mark.parametrize(
    "fetch_items",
    [
        {
            "type": "rezka",
            "parser": RezkaFeed,
            "url": "https://hdrezka.me/series/comedy/7670-sashatanya-2013-latest.html",
        }
    ],
    indirect=True,
)
async def test_rezka_many_items(fetch_items):  # noqa: F811
    assert len(fetch_items) > 0
    assert len(fetch_items) < 100
