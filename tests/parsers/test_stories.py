import pytest

from app.parsers.stories import InstagramStoriesFeed
from . import fetch_items  # noqa

STORIES_FEED_DATA = {
    "type": "stories",
    "parser": InstagramStoriesFeed,
    "url": "https://www.instagram.com/werrvin",
}


@pytest.mark.parametrize("fetch_items", [STORIES_FEED_DATA], indirect=True)
async def test_stories_feed(fetch_items):  # noqa: F811
    assert isinstance(fetch_items, list)
    assert all(item.link.startswith("http") for item in fetch_items)
