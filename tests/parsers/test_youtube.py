import pytest
from app.parsers.youtube import YoutubeFeed
from . import fetch_items  # noqa

YOUTUBE_FEED_DATA = {
    "type": "yt",
    "parser": YoutubeFeed,
    "url": "https://www.youtube.com/channel/UCJM8s_4MRZF7CgIxM84d0cg",
}


@pytest.mark.parametrize("fetch_items", [YOUTUBE_FEED_DATA], indirect=True)
async def test_youtube_feed(fetch_items):
    assert len(await fetch_items) != 0
