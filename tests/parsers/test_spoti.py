import pytest
from app.parsers.spoti import SpotifyFeed, SpotifyPlaylistFeed
from . import fetch_items  # noqa

SPOTIFY_FEED_DATA = {
    "type": "spoti",
    "parser": SpotifyFeed,
    "url": "https://open.spotify.com/artist/4t8lDh2zuWn1d9cyJQkESe",
}

SPOTIFY_PLAYLIST_FEED_DATA = {
    "type": "spoti:playlist",
    "parser": SpotifyPlaylistFeed,
    "url": "https://open.spotify.com/playlist/37i9dQZEVXbeUwP0nygk6B",
}


@pytest.mark.parametrize("fetch_items", [SPOTIFY_FEED_DATA], indirect=True)
async def test_spoti_feed(fetch_items):
    assert len(await fetch_items) != 0


@pytest.mark.parametrize("fetch_items", [SPOTIFY_PLAYLIST_FEED_DATA], indirect=True)
async def test_spoti_playlist_feed(fetch_items):
    assert len(await fetch_items) != 0
