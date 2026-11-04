from datetime import UTC, datetime, timedelta
from math import isfinite
from typing import Any

import structlog

from app.core.worker_kind import WorkerKind
from app.extensions.parsers.exceptions import FeedUnavailable
from app.services.ytdlp.extractor import YtdlpInfoExtractor
from app.services.ytdlp.modes import (
    TikTokProfileExtractionMode,
    TikTokVideoExtractionMode,
)

from ._base import BaseTikTokFeed

logger = structlog.get_logger(__name__)


class TikTokFeed(BaseTikTokFeed):
    worker_kind = WorkerKind.LIGHT
    _max_videos = 10
    _empty_confirmed_cache_time = timedelta(days=3)
    _entries_by_url: dict[str, dict[str, Any]]

    @property
    async def _video_links(self) -> list[str]:
        self.data.pop("retry_at", None)
        self._entries_by_url = {}
        info = await YtdlpInfoExtractor.extract_channel_videos_info(
            self.feed.url, TikTokProfileExtractionMode(), self._max_videos
        )
        if info.get("tiktok_outcome") == "partial" or info.get("extraction_incomplete"):
            raise FeedUnavailable(self.feed.url, "tiktok_profile_extraction_failed")

        entries = info["entries"]
        if not isinstance(entries, list):
            raise TypeError("TikTok discovery did not return an entries list")
        if not entries and info.get("tiktok_outcome") != "empty_confirmed":
            raise FeedUnavailable(self.feed.url, "tiktok_profile_empty_unverified")
        if entries and info.get("tiktok_outcome") == "empty_confirmed":
            raise ValueError("Confirmed empty TikTok profile contains video entries")
        if info.get("tiktok_outcome") == "empty_confirmed":
            self.data["retry_at"] = datetime.now(UTC) + self._empty_confirmed_cache_time

        videos: list[str] = []
        for index, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                raise TypeError(f"TikTok entry {index} is not a video object")
            url = entry.get("url") or entry.get("webpage_url")
            if not isinstance(url, str) or not url.strip():
                raise ValueError(f"TikTok entry {index} has no valid video URL")
            videos.append(url)
            self._entries_by_url[url] = entry

        logger.info(
            "tiktok_discovery_completed",
            outcome="links_found" if videos else "empty_confirmed",
            requested_limit=self._max_videos,
            entries=len(entries),
            links=len(videos),
            below_limit=len(videos) < self._max_videos,
        )
        return videos

    async def _get_video_info(self, link: str) -> dict[str, Any]:
        info = self._entries_by_url.get(link, {})
        if self._has_item_metadata(info):
            return info

        info = await YtdlpInfoExtractor.get_info(link, TikTokVideoExtractionMode())
        if not self._has_item_metadata(info):
            raise ValueError("TikTok video metadata is incomplete")
        return info

    @staticmethod
    def _has_item_metadata(info: dict[str, Any]) -> bool:
        timestamp = info.get("timestamp")
        return (
            isinstance(info.get("description"), str)
            and isinstance(timestamp, (int, float))
            and not isinstance(timestamp, bool)
            and isfinite(timestamp)
        )
