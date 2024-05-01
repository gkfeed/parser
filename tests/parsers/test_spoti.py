import pytest

from app.serializers.feed import Feed
from app.parsers.spoti import SpotifyFeed, SpotifyPlaylistFeed
from . import FakeDispatcher


async def test_spoti_feed():
    dp = FakeDispatcher()

    feed = Feed(
        id=1,
        title="x",
        type="spoti",
        url="https://open.spotify.com/artist/4t8lDh2zuWn1d9cyJQkESe",
    )

    dp.register_parser("spoti", SpotifyFeed)
    await dp.fetch_feed(feed)

    # test if parser actually works
    assert len(dp.items) != 0


async def test_spoti_playlist_feed():
    dp = FakeDispatcher()

    feed = Feed(
        id=1,
        title="x",
        type="spoti:playlist",
        url="https://open.spotify.com/playlist/37i9dQZEVXbeUwP0nygk6B",
    )

    dp.register_parser("spoti:playlist", SpotifyPlaylistFeed)
    await dp.fetch_feed(feed)

    # test if parser actually works
    assert len(dp.items) != 0
