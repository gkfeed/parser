from datetime import timedelta
from typing import NamedTuple

from app.services.cache.use_temporary import (
    UseTemporaryCacheServiceExtension,
    async_store_in_cache_for,
)
from app.workers.youtube import extract_info

from .modes import BaseExtractionMode, VideoExtractionMode


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
            return cls.cache.get(cache_id)

        info = await cls.get_info(videos_url, extraction_mode, max_videos=max_videos)
        limited_info = {**info, "entries": info.get("entries", [])[:max_videos]}
        cls.cache.set_with_expiry(
            cache_id, limited_info, cls._channel_info_storage_time
        )
        return limited_info

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
