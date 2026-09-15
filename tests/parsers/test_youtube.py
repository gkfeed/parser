import pytest

from app.parsers.youtube import YoutubeFeed

from . import fetch_items  # noqa

YOUTUBE_FEEDS = [
    pytest.param(
        {
            "type": "yt",
            "parser": YoutubeFeed,
            "url": "https://www.youtube.com/@YouTube",
        },
        id="handle-root",
    ),
    pytest.param(
        {
            "type": "yt",
            "parser": YoutubeFeed,
            "url": "https://www.youtube.com/@YouTube/?view=0",
        },
        id="handle-root-with-query",
    ),
    pytest.param(
        {
            "type": "yt",
            "parser": YoutubeFeed,
            "url": "https://www.youtube.com/channel/UCBR8-60-B28hp2BmDPdntcQ/",
        },
        id="channel-id-root",
    ),
    pytest.param(
        {
            "type": "yt",
            "parser": YoutubeFeed,
            "url": "https://www.youtube.com/@YouTube/videos",
        },
        id="videos-tab",
    ),
    pytest.param(
        {
            "type": "yt",
            "parser": YoutubeFeed,
            "url": "https://www.youtube.com/@YouTube/shorts",
        },
        id="shorts-tab",
    ),
    pytest.param(
        {
            "type": "yt",
            "parser": YoutubeFeed,
            "url": "https://www.youtube.com/@YouTube/streams",
        },
        id="streams-tab",
    ),
    pytest.param(
        {
            "type": "yt",
            "parser": YoutubeFeed,
            "url": (
                "https://www.youtube.com/playlist"
                "?list=PLByBwjzaem--xY_y6goiiW3CovivhDLsi"
            ),
        },
        id="playlist",
    ),
]


@pytest.mark.parametrize("fetch_items", YOUTUBE_FEEDS, indirect=True)
async def test_youtube_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) != 0
