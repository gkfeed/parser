from datetime import UTC, datetime, timedelta
from math import isfinite
from typing import Any

import structlog

from app.core.worker_kind import WorkerKind
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
    _entries_by_url: dict[str, dict[str, Any]]

    @property
    async def _video_links(self) -> list[str]:
        self.data.pop("retry_at", None)
        self._entries_by_url = {}
        info = await YtdlpInfoExtractor.extract_channel_videos_info(
            self.feed.url, TikTokProfileExtractionMode(), self._max_videos
        )
        if info.get("tiktok_outcome") == "partial":
            self.data["retry_at"] = datetime.now(UTC) + timedelta(minutes=15)

        entries = info["entries"]
        videos: list[str] = []
        for index, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                logger.warning(
                    "tiktok_entry_skipped",
                    entry_index=index,
                    reason="invalid_entry_type",
                    entry_type=type(entry).__name__,
                )
                continue
            url = entry.get("url") or entry.get("webpage_url")
            if not isinstance(url, str) or not url.strip():
                logger.warning(
                    "tiktok_entry_skipped", entry_index=index, reason="invalid_url"
                )
                continue
            videos.append(url)
            self._entries_by_url[url] = entry

        skipped = len(entries) - len(videos)
        if skipped:
            self.data["retry_at"] = datetime.now(UTC) + timedelta(minutes=15)
        outcome = "links_found"
        if not videos:
            outcome = "no_valid_entries" if entries else "no_entries"
        log = logger.warning if skipped or not videos else logger.info
        log(
            "tiktok_discovery_completed",
            outcome=outcome,
            requested_limit=self._max_videos,
            entries=len(entries),
            links=len(videos),
            skipped=skipped,
            below_limit=len(videos) < self._max_videos,
        )
        if entries and not videos:
            raise ValueError("TikTok discovery returned no valid video links")
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
