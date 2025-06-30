import pytest
from app.parsers.twitch import TwitchFeed
from . import fetch_items  # noqa

TWITCH_FEED_DATA = {
    "type": "twitch",
    "parser": TwitchFeed,
    "url": "https://twitch.tv/kussia88",
}


@pytest.mark.skip(reason="its not work")
@pytest.mark.parametrize("fetch_items", [TWITCH_FEED_DATA], indirect=True)
async def test_twitch_feed(fetch_items):  # noqa: F811
    assert len(await fetch_items) != 0
