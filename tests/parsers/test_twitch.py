import pytest

from app.serializers.feed import Feed
from app.parsers.twitch import TwitchFeed
from . import FakeDispatcher


@pytest.mark.skip(reason="its not work")
async def test_twitch_feed():
    dp = FakeDispatcher()

    feed = Feed(
        id=1,
        title="x",
        type="twitch",
        url="https://twitch.tv/kussia88",
    )

    dp.register_parser("twitch", TwitchFeed)
    await dp.fetch_feed(feed)

    # test if parser actually works
    assert len(dp.items) != 0
