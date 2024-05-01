from app.serializers.feed import Feed
from app.parsers.insolarance import InsolaranceFeed
from . import FakeDispatcher


async def test_insolarance_feed():
    dp = FakeDispatcher()

    feed = Feed(
        id=1,
        title="x",
        type="insolarance",
        url="https://insolarance.com",
    )

    dp.register_parser("insolarance", InsolaranceFeed)
    await dp.fetch_feed(feed)

    # test if parser actually works
    assert len(dp.items) != 0
