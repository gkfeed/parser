from app.serializers.feed import Feed
from app.parsers.ranobeme import RanobeMeFeed
from . import FakeDispatcher


async def test_ranobeme_feed():
    dp = FakeDispatcher()

    feed = Feed(
        id=1,
        title="x",
        type="ranobeme",
        url="https://ranobe.me/ranobe166",
    )

    dp.register_parser("ranobeme", RanobeMeFeed)
    await dp.fetch_feed(feed)

    # test if parser actually works
    assert len(dp.items) != 0
