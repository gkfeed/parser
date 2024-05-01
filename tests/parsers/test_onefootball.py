from app.serializers.feed import Feed
from app.parsers.onefootball import OneFootballFeed
from . import FakeDispatcher


async def test_onefootball_feed():
    dp = FakeDispatcher()

    feed = Feed(
        id=1,
        title="x",
        type="onefootball",
        url="https://onefootball.com/en/team/barcelona-5",
    )

    dp.register_parser("onefootball", OneFootballFeed)
    await dp.fetch_feed(feed)

    # test if parser actually works
    assert len(dp.items) != 0

    # test if parser works correctly it must return only 2 items
    assert len(dp.items) == 2
