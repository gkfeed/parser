from app.serializers.feed import Feed
from app.parsers.vk import VkFeed
from . import FakeDispatcher


async def test_vk_feed():
    dp = FakeDispatcher()

    feed = Feed(
        id=1,
        title="x",
        type="vk",
        url="https://vk.com/rhymes",
    )

    dp.register_parser("vk", VkFeed)
    await dp.fetch_feed(feed)

    # test if parser actually works
    assert len(dp.items) != 0
