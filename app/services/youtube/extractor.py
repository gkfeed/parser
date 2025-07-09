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


class YoutubeInfoExtractor(UseTemporaryCacheServiceExtension):
    _channel_info_storage_time = timedelta(hours=1)
    _video_info_storage_time = timedelta(weeks=1)

    @classmethod
    @async_store_in_cache_for(_video_info_storage_time)
    async def extract_video_info(cls, url: str) -> VideoInfo:
        info = await cls._get_info(url, VideoExtractionMode())
        return VideoInfo(info["title"], info["upload_date"], info["uploader"])

    @classmethod
    @async_store_in_cache_for(_channel_info_storage_time)
    async def extract_channel_videos_info(
        cls, videos_url: str, extraction_mode: BaseExtractionMode, max_videos: int
    ) -> dict:
        return await cls._get_info(videos_url, extraction_mode)

    @classmethod
    @async_store_in_cache_for(_channel_info_storage_time)
    async def extract_video_urls(
        cls, videos_url: str, extraction_mode: BaseExtractionMode, max_videos: int
    ) -> list[str]:
        info = await cls._get_info(videos_url, extraction_mode)
        return [v["url"] for v in info["entries"][-max_videos:]]

    @classmethod
    async def _get_info(
        cls,
        url: str,
        mode: BaseExtractionMode = BaseExtractionMode(),
        keys: list[str] | None = None,
    ) -> dict:
        return await extract_info(url, mode.opts, keys)
