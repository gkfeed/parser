import pytest
from app.parsers.spoti import SpotifyFeed, SpotifyPlaylistFeed
from . import fetch_items  # noqa

SPOTIFY_FEED_DATA = {
    "type": "spoti",
    "parser": SpotifyFeed,
    # "url": "https://open.spotify.com/artist/4t8lDh2zuWn1d9cyJQkESe",
    "url": "https://open.spotify.com/artist/3Fl31gc0mEUC2H0JWL1vic/",
}

SPOTIFY_PLAYLIST_FEED_DATA = [
    {
        "type": "spoti:playlist",
        "parser": SpotifyPlaylistFeed,
        "url": "https://open.spotify.com/playlist/37i9dQZEVXbeUwP0nygk6B",
    },
    {
        "type": "spoti:playlist",
        "parser": SpotifyPlaylistFeed,
        "url": "https://open.spotify.com/playlist/37i9dQZEVXcO6Skt3MisbU",
    },
]


@pytest.mark.parametrize("fetch_items", [SPOTIFY_FEED_DATA], indirect=True)
async def test_spoti_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) != 0


@pytest.mark.parametrize("fetch_items", SPOTIFY_PLAYLIST_FEED_DATA, indirect=True)
async def test_spoti_playlist_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) != 0
