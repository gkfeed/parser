import pytest
from app.parsers.vk import VkFeed
from . import fetch_items  # noqa

VK_FEED_DATA = [
    {"type": "vk", "parser": VkFeed, "url": "https://vk.com/rhymes"},
    {"type": "vk", "parser": VkFeed, "url": "https://vk.com/lolwildrift"},
]


@pytest.mark.parametrize("fetch_items", VK_FEED_DATA, indirect=True)
async def test_vk_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) != 0
    for item in fetch_items:
        assert item.title
        # Group posts must have a minus sign in the wall link
        assert item.link.startswith("https://vk.com/wall-")
