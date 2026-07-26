import pytest

from app.configs.env import TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET
from app.parsers.twitch import TwitchFeed

from . import fetch_items  # noqa

TWITCH_FEED_DATA = {
    "type": "twitch",
    "parser": TwitchFeed,
    "url": "https://twitch.tv/kussia88",
}


@pytest.mark.skipif(
    TWITCH_CLIENT_ID == "dummy" or TWITCH_CLIENT_SECRET == "dummy",
    reason="requires real Twitch API credentials",
)
@pytest.mark.parametrize("fetch_items", [TWITCH_FEED_DATA], indirect=True)
async def test_twitch_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) != 0
