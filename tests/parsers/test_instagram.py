from app.serializers.feed import Feed
from app.parsers.instagram import InstagramFeed
from . import FakeDispatcher


async def test_instagram_feed():
    dp = FakeDispatcher()
    feed = Feed(
        id=1,
        title="x",
        type="inst",
        url="https://www.instagram.com/makaryshaa",
    )

    dp.register_parser("inst", InstagramFeed)
    await dp.fetch_feed(feed)

    # test if parser actually works
    assert len(dp.items) != 0
