from collections.abc import Generator
from typing import Any, ClassVar, Self

import pytest

from app.parsers.tiktok import TikTokFeed
from app.parsers.youtube import YoutubeFeed
from app.serializers.feed import Feed
from app.services.ytdlp.extractor import YtdlpInfoExtractor
from app.services.ytdlp.modes import (
    BaseExtractionMode,
    ChannelExtractionMode,
    PlaylistExtractionMode,
)


class FakeYoutubeDL:
    calls: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, options: dict[str, Any]) -> None:
        self.options = options

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def extract_info(self, url: str, *, download: bool) -> dict[str, Any]:
        self.calls.append({"url": url, "options": self.options, "download": download})
        if "/video/" in url:
            return {"description": url, "timestamp": 1_700_000_000}

        entries = [
            {
                "title": f"Video {number}",
                "url": f"{url}/video/{number}",
                "timestamp": 1_700_000_000 + number,
            }
            for number in range(12)
        ]
        return {"channel": "Test channel", "entries": entries}


@pytest.fixture
def fake_youtube_dl(monkeypatch) -> Generator[type[FakeYoutubeDL], None, None]:
    FakeYoutubeDL.calls = []
    monkeypatch.setattr("app.workers.youtube.yt_dlp.YoutubeDL", FakeYoutubeDL)
    yield FakeYoutubeDL


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.test/@channel/videos",
        "https://www.youtube.test/playlist?list=123",
    ],
)
async def test_youtube_limits_channel_and_playlist_results(
    url: str, fake_youtube_dl: type[FakeYoutubeDL]
) -> None:
    feed = Feed(id=1, title="YouTube", type="yt", url=url)

    items = await YoutubeFeed(feed, {}).items

    assert len(items) == 5
    assert fake_youtube_dl.calls[0]["options"]["playlist_items"] == "1-5"


async def test_tiktok_limits_channel_extraction(
    fake_youtube_dl: type[FakeYoutubeDL],
) -> None:
    url = "https://www.tiktok.test/@channel"
    feed = Feed(id=1, title="TikTok", type="tiktok", url=url)

    items = await TikTokFeed(feed, {}).items

    assert len(items) == 10
    channel_call = next(call for call in fake_youtube_dl.calls if call["url"] == url)
    assert channel_call["options"]["playlist_items"] == "1-10"


async def test_channel_cache_separates_mode_and_limit(
    fake_youtube_dl: type[FakeYoutubeDL],
) -> None:
    url = "https://www.youtube.test/@channel/videos"

    one_video = await YtdlpInfoExtractor.extract_channel_videos_info(
        url, ChannelExtractionMode(), 1
    )
    two_videos = await YtdlpInfoExtractor.extract_channel_videos_info(
        url, ChannelExtractionMode(), 2
    )
    playlist = await YtdlpInfoExtractor.extract_channel_videos_info(
        url, PlaylistExtractionMode(), 2
    )
    cached = await YtdlpInfoExtractor.extract_channel_videos_info(
        url, ChannelExtractionMode(), 2
    )

    assert len(one_video["entries"]) == 1
    assert len(two_videos["entries"]) == 2
    assert len(playlist["entries"]) == 2
    assert cached == two_videos
    assert len(fake_youtube_dl.calls) == 3


@pytest.mark.parametrize("max_videos", [0, -1])
async def test_channel_limit_must_be_positive(max_videos: int) -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        await YtdlpInfoExtractor.extract_channel_videos_info(
            "https://www.tiktok.test/@channel",
            BaseExtractionMode(),
            max_videos,
        )
