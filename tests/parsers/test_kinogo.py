from app.serializers.feed import Feed
from app.parsers.kinogo import KinogoFeed
from . import FakeDispatcher


async def test_insolarance_feed():
    dp = FakeDispatcher()
    feed = Feed(
        id=1,
        title="x",
        type="kinogo",
        url="https://kinogo.fm/631-.html",
    )

    dp.register_parser("kinogo", KinogoFeed)
    await dp.fetch_feed(feed)

    # test if parser actually works
    assert len(dp.items) != 0
