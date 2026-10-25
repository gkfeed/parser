from copy import deepcopy
from datetime import UTC, datetime

import pytest

from app.extensions.parsers.exceptions import FeedUnavailable
from app.parsers.tiktok import TikTokFeed
from app.serializers.feed import Feed

PROFILE_URL = "https://www.tiktok.test/@fixture"


def video(number):
    return {
        "url": f"{PROFILE_URL}/video/{number}",
        "description": f"Fixture video {number}",
        "timestamp": 1_700_000_000 + number,
    }


class ExtractorBoundary:
    """Fixed yt-dlp results; parsing, classification and caching stay real."""

    def __init__(self):
        self.results = {PROFILE_URL: {"entries": [video(0)]}}
        self.errors = {}
        self.calls = []

    def youtube_dl(self, options):
        return YoutubeDLSession(self, options)


class YoutubeDLSession:
    def __init__(self, boundary, options):
        self.boundary = boundary
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, *, download):
        assert download is False
        self.boundary.calls.append(url)
        if url in self.boundary.errors:
            self.options["logger"].error(self.boundary.errors[url])
        return deepcopy(self.boundary.results[url])


@pytest.fixture
def extractor(monkeypatch):
    boundary = ExtractorBoundary()
    monkeypatch.setattr("app.workers.youtube.yt_dlp.YoutubeDL", boundary.youtube_dl)
    return boundary


def parser():
    return TikTokFeed(Feed(id=1, title="TikTok", type="tiktok", url=PROFILE_URL), {})


@pytest.mark.parametrize("count", [1, 14])
async def test_channel_results_become_items_and_respect_video_limit(extractor, count):
    extractor.results[PROFILE_URL] = {"entries": [video(n) for n in range(count)]}

    items = await parser().items

    expected_count = min(count, 10)
    assert [item.link for item in items] == [
        video(n)["url"] for n in range(expected_count)
    ]
    assert [item.title for item in items] == [
        f"Fixture video {n}" for n in range(expected_count)
    ]
    assert all(item.text == item.title for item in items)
    assert items[0].date == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)


async def test_flat_entries_fetch_video_metadata_and_accept_webpage_url(extractor):
    first, second = video(1), video(2)
    extractor.results[PROFILE_URL] = {
        "entries": [{"url": first["url"]}, {"webpage_url": second["url"]}]
    }
    extractor.results[first["url"]] = first
    extractor.results[second["url"]] = second

    items = await parser().items

    assert [item.title for item in items] == [
        first["description"],
        second["description"],
    ]
    assert [item.link for item in items] == [first["url"], second["url"]]
    assert set(extractor.calls) == {PROFILE_URL, first["url"], second["url"]}


@pytest.mark.parametrize(
    ("message", "reason"),
    [
        ("Unable to extract secondary user ID", "tiktok_profile_unavailable"),
        ("This account is private", "tiktok_profile_restricted"),
        ("Unexpected upstream failure", "tiktok_profile_extraction_failed"),
    ],
)
async def test_ytdlp_failure_is_translated_to_feed_failure(extractor, message, reason):
    extractor.results[PROFILE_URL] = None
    extractor.errors[PROFILE_URL] = message

    with pytest.raises(FeedUnavailable) as raised:
        await parser().items

    assert raised.value.reason == reason
    assert raised.value.url == PROFILE_URL
    assert raised.value.retry_at is not None


async def test_partial_extraction_raises_instead_of_publishing_incomplete_items(
    extractor,
):
    extractor.errors[PROFILE_URL] = "Pagination failed"

    with pytest.raises(FeedUnavailable, match="tiktok_profile_extraction_failed"):
        await parser().items


@pytest.mark.parametrize("missing_url", [{}, {"url": ""}, {"url": "  "}, {"url": 123}])
async def test_missing_video_url_aborts_the_feed(extractor, missing_url):
    extractor.results[PROFILE_URL] = {"entries": [video(0), missing_url]}

    with pytest.raises(ValueError, match="no valid video URL"):
        await parser().items


async def test_confirmed_empty_profile_returns_empty(extractor):
    extractor.results[PROFILE_URL] = None
    extractor.errors[PROFILE_URL] = "This account does not have any videos posted"

    assert await parser().items == []


async def test_unverified_empty_profile_raises(extractor):
    extractor.results[PROFILE_URL] = {"entries": []}

    with pytest.raises(FeedUnavailable, match="tiktok_profile_empty_unverified"):
        await parser().items
