import pytest

from app.parsers.vkvideo import VkVideoFeed

from . import fetch_items  # noqa

VKVIDEO_FEED_DATA = [
    {
        "type": "vkvideo",
        "parser": VkVideoFeed,
        "url": "https://vkvideo.ru/@algoritm_101",
    }
]


@pytest.mark.parametrize("fetch_items", VKVIDEO_FEED_DATA, indirect=True)
async def test_vkvideo_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) != 0
    for item in fetch_items:
        assert item.text
        assert item.link.startswith("https://vkvideo.ru/video")
