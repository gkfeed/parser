import pytest
from bs4 import BeautifulSoup

from app.parsers.vk import VkFeed
from app.serializers.feed import Feed

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


@pytest.mark.asyncio
async def test_vk_post_keeps_photo_in_item_text():
    post = BeautifulSoup(
        """
        <article data-testid="post" data-post-id="-123_456">
          <div data-testid="showmoretext-in-456">Post &amp; description</div>
          <a href="/photo-123_789">
            <img src="https://sun9-67.userapi.com/impg/preview.jpg?size=1280x960">
          </a>
        </article>
        """,
        "html.parser",
    ).article
    assert post is not None

    parser = VkFeed(
        Feed(id=1, title="VK", type="vk", url="https://vk.com/example"),
        {},
    )

    assert await parser._get_post_text(post) == (
        '<img src="https://sun9-67.userapi.com/impg/preview.jpg?size=1280x960" '
        'alt="VK post"><br>Post &amp; description'
    )
