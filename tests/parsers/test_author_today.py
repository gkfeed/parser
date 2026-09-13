import pytest

from app.parsers.author_today import AuthorTodayFeed

from . import fetch_items  # noqa: F401

AUTHOR_TODAY_FEED_DATA = {
    "type": "author.today",
    "parser": AuthorTodayFeed,
    "url": "https://author.today/work/572901",
}


@pytest.mark.parametrize("fetch_items", [AUTHOR_TODAY_FEED_DATA], indirect=True)
async def test_author_today_live_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) != 0
