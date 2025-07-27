import pytest
from app.parsers.anilibria import AnilibriaFeed
from . import fetch_items  # noqa

ANILIBRIA_FEED_DATA = [
    {
        "type": "anilibria",
        "parser": AnilibriaFeed,
        "url": "https://anilibria.top/anime/releases/release/dr-stone-science-future-part-2/episodes",
    },
]


@pytest.mark.parametrize("fetch_items", ANILIBRIA_FEED_DATA, indirect=True)
async def test_anilibria_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) != 0
