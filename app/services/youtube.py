from datetime import timedelta

import yt_dlp  # type: ignore

from app.services.queue import async_queue_wrap
from app.services.cache.use_temporary import (
    UseTemporaryCacheServiceExtension,
    async_store_in_cache_for,
)


class BaseExtractionMode:
    opts = {
        "ignoreerrors": True,
        "quiet": True,
        "lazy_playlist": False,
        "extract_flat": True,
    }


class ChannelExtractionMode(BaseExtractionMode):
    max_videos = 5
    opts = {
        "ignoreerrors": True,
        "quiet": True,
        "lazy_playlist": False,
        "extract_flat": True,
        "playlist_items": f"1-{max_videos}",
        "extractor_args": {
            "youtubetab": {
                "approximate_date": "upload_date",
            }
        },
    }


class VideoExtractionMode(BaseExtractionMode):
    opts = {
        "ignoreerrors": True,
        "quiet": True,
        "extract_flat": False,
        "skip_download": True,
        "extractorargs": {
            "youtube": {
                "player_skip": ["js", "webpage", "configs"],
                "skip": ["hls", "dash", "translated_tabs"],
            }
        },
    }


class PlaylistExtractionMode(BaseExtractionMode):
    opts = {
        "ignoreerrors": True,
        "quiet": True,
        "lazy_playlist": False,
        "extract_flat": False,
        # "playlist_items": f"90-100",
        "extractor_args": {
            "youtubetab": {
                "approximate_date": "upload_date",
            }
        },
    }


class YoutubeInfoExtractor(UseTemporaryCacheServiceExtension):
    _channel_info_storage_time = timedelta(hours=1)
    _video_info_storage_time = timedelta(weeks=1)

    @classmethod
    @async_store_in_cache_for(_video_info_storage_time)
    async def get_info(
        cls, url: str, mode: BaseExtractionMode = BaseExtractionMode()
    ) -> dict:
        return await cls.extract_info(url, mode.opts)

    @async_queue_wrap
    def extract_info(url: str, opts: dict) -> dict:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            raise ValueError
        return info
