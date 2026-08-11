from unittest.mock import AsyncMock, patch

import pytest
from bs4 import BeautifulSoup

from app.parsers.spoti import SpotifyFeed, SpotifyPlaylistFeed
from app.serializers.feed import Feed

from . import fetch_items  # noqa

SPOTIFY_FEED_DATA = [
    {
        "type": "spoti",
        "parser": SpotifyFeed,
        "url": "https://open.spotify.com/artist/3Fl31gc0mEUC2H0JWL1vic/",
    },
    {
        "type": "spoti",
        "parser": SpotifyFeed,
        "url": "https://open.spotify.com/artist/0ChMIwzbYxHbebgoPeETfV",
    },
]

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


@pytest.mark.parametrize("fetch_items", SPOTIFY_FEED_DATA, indirect=True)
async def test_spoti_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) != 0


@pytest.mark.parametrize("fetch_items", SPOTIFY_PLAYLIST_FEED_DATA, indirect=True)
async def test_spoti_playlist_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) != 0


def test_spoti_playlist_extracts_first_track_by_link():
    soup = BeautifulSoup(
        """
        <main>
          <img src="playlist-cover.jpg">
          <img src="playlist-owner.jpg">
          <div class="track-row">
            <img src="track-cover.jpg">
            <div><a href="/track/track-id?si=abc"><div>Track name</div></a></div>
            <span>
              <a href="/artist/first-artist">First artist</a>
              <a href="/artist/second-artist">Second artist</a>
            </span>
          </div>
        </main>
        """,
        "html.parser",
    )
    parser = SpotifyPlaylistFeed(
        Feed(id=1, title="Playlist", url="https://example.com", type="spoti"), {}
    )

    track = parser._get_first_track_element(soup)
    anchor = parser._get_track_anchor_tag(track)

    assert parser._get_track_name(anchor) == "Track name"
    assert parser._get_track_artist(anchor) == "First artist, Second artist"
    assert parser._get_track_id(anchor) == "track-id"


def test_spoti_playlist_requires_track_link():
    soup = BeautifulSoup('<a href="/artist/artist-id">Artist</a>', "html.parser")
    parser = SpotifyPlaylistFeed(
        Feed(id=1, title="Playlist", url="https://example.com", type="spoti"), {}
    )

    with pytest.raises(ValueError, match="first track"):
        parser._get_first_track_element(soup)


async def test_spoti_artist_parses_discography_items():
    soup = BeautifulSoup(
        """
        <meta property="og:title" content="Artist name">
        <a href="/album/album-id">Album name</a>
        """,
        "html.parser",
    )
    parser = SpotifyFeed(
        Feed(
            id=1,
            title="Artist",
            url="https://open.spotify.com/artist/artist-id",
            type="spoti",
        ),
        {},
    )

    with patch.object(parser, "get_soup", AsyncMock(return_value=soup)):
        items = await parser.items

    assert [(item.title, item.text, item.link) for item in items] == [
        (
            "Artist name - Album name",
            "Album name",
            "https://open.spotify.com/album/album-id",
        )
    ]
