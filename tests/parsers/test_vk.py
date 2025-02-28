import pytest
from app.parsers.vk import VkFeed
from . import fetch_items  # noqa

VK_FEED_DATA = {"type": "vk", "parser": VkFeed, "url": "https://vk.com/rhymes"}


@pytest.mark.parametrize("fetch_items", [VK_FEED_DATA], indirect=True)
async def test_vk_feed(fetch_items):
    assert len(await fetch_items) != 0
