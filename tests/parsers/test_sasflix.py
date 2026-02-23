import pytest
from app.parsers.sasflix import SasflixFeed
from . import fetch_items  # noqa


SASFLIX_FEEDS = [
    {
        "type": "sasflix",
        "parser": SasflixFeed,
        "url": "https://sasflix.ru/",
    },
]


@pytest.mark.parametrize("fetch_items", SASFLIX_FEEDS, indirect=True)
async def test_sasflix_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) > 0
    for item in fetch_items:
        assert item.title
        assert item.link
        assert item.text
        assert item.date
