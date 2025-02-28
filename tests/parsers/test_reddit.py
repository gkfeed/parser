import pytest
from app.parsers.reddit import RedditFeed
from . import fetch_items  # noqa

REDDIT_FEED_DATA = {
    "type": "reddit",
    "parser": RedditFeed,
    "url": "https://www.reddit.com/r/neovim",
}


@pytest.mark.parametrize("fetch_items", [REDDIT_FEED_DATA], indirect=True)
async def test_reddit_feed(fetch_items):
    assert len(await fetch_items) != 0
