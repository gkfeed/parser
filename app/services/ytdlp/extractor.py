from datetime import timedelta
from typing import NamedTuple

import structlog

from app.services.cache.use_temporary import (
    UseTemporaryCacheServiceExtension,
    async_store_in_cache_for,
)
from app.workers.youtube import extract_info

from .modes import BaseExtractionMode, VideoExtractionMode

logger = structlog.get_logger(__name__)


class VideoInfo(NamedTuple):
    title: str
    upload_date_str: str
    channel_name: str


class YtdlpInfoExtractor(UseTemporaryCacheServiceExtension):
    _channel_info_storage_time = timedelta(hours=1)
    _video_info_storage_time = timedelta(weeks=1)

    @classmethod
    @async_store_in_cache_for(_video_info_storage_time)
    async def extract_video_info(cls, url: str) -> VideoInfo:
        info = await cls.get_info(url, VideoExtractionMode())
        return VideoInfo(info["title"], info["upload_date"], info["uploader"])

    @classmethod
    async def extract_channel_videos_info(
        cls, videos_url: str, extraction_mode: BaseExtractionMode, max_videos: int
    ) -> dict:
        """Return at most ``max_videos`` entries and limit yt-dlp to that count."""
        if max_videos <= 0:
            raise ValueError("max_videos must be greater than zero")

        cache_id = f"{videos_url}::{type(extraction_mode).__qualname__}::{max_videos}"
        if cls.cache.has_valid_cache(cache_id):
            cached_info = cls.cache.get(cache_id)
            cached_entries = cached_info.get("entries")
            if cls._can_cache_entries(cached_entries):
                logger.info(
                    "channel_discovery_completed",
                    source="cache",
                    requested_limit=max_videos,
                    entries=len(cached_entries),
                )
                return cached_info
            logger.warning(
                "channel_discovery_cache_ignored",
                source="cache",
                reason="empty_or_invalid_entries",
            )

        info = await cls.get_info(videos_url, extraction_mode, max_videos=max_videos)
        entries = info.get("entries")
        if not isinstance(entries, list):
            logger.error(
                "channel_discovery_failed",
                reason="invalid_entries_type",
                entries_type=type(entries).__name__,
            )
            raise TypeError("Channel extraction did not return an entries list")

        selected_entries = entries[:max_videos]
        limited_info = {**info, "entries": selected_entries}
        cacheable = cls._can_cache_entries(selected_entries)
        log = logger.info if cacheable else logger.warning
        log(
            "channel_discovery_completed",
            source="yt_dlp",
            requested_limit=max_videos,
            entries=len(entries),
            selected=len(selected_entries),
            cacheable=cacheable,
        )
        if cacheable:
            cls.cache.set_with_expiry(
                cache_id, limited_info, cls._channel_info_storage_time
            )
        return limited_info

    @staticmethod
    def _can_cache_entries(entries: object) -> bool:
        if not isinstance(entries, list) or not entries:
            return False
        for entry in entries:
            if not isinstance(entry, dict):
                return False
            url = entry.get("url") or entry.get("webpage_url")
            if not isinstance(url, str) or not url.strip():
                return False
        return True

    @classmethod
    async def extract_video_urls(
        cls, videos_url: str, extraction_mode: BaseExtractionMode, max_videos: int
    ) -> list[str]:
        info = await cls.extract_channel_videos_info(
            videos_url, extraction_mode, max_videos
        )
        return [v["url"] for v in info["entries"]]

    @classmethod
    async def get_info(
        cls,
        url: str,
        mode: BaseExtractionMode | None = None,
        keys: list[str] | None = None,
        max_videos: int | None = None,
    ) -> dict:
        if mode is None:
            mode = BaseExtractionMode()
        return await extract_info(url, mode.options(max_videos), keys)
