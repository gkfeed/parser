from typing import Any
from datetime import timedelta

import yt_dlp  # type: ignore

from app.services.queue import async_queue_wrap
from app.services.cache.use_temporary import (
    UseTemporaryCacheServiceExtension,
    async_store_in_cache_for,
)


class BaseExtractionMode:
    opts: dict[str, Any] = {
        "socket_timeout": 60,
        "ignoreerrors": True,
        "quiet": True,
        "lazy_playlist": False,
        "extract_flat": True,
    }


class ChannelExtractionMode(BaseExtractionMode):
    max_videos = 5
    opts: dict[str, Any] = {
        "socket_timeout": 60,
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
    opts: dict[str, Any] = {
        "socket_timeout": 60,
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
    opts: dict[str, Any] = {
        "socket_timeout": 60,
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
        cls,
        url: str,
        mode: BaseExtractionMode = BaseExtractionMode(),
        keys: list[str] | None = None,
    ) -> dict:
        return cls.extract_info(url, mode.opts, keys)
        return await async_queue_wrap(cls.extract_info)(url, mode.opts, keys)

    # @async_queue_wrap
    @classmethod
    def extract_info(cls, url: str, opts: dict, keys: list[str] | None = None) -> dict:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if keys:
                _info = {}
                for key in keys:
                    _info[key] = info[key]
                info = _info

                # info["automatic_captions"] = None
                # for key in info["automatic_captions"]:
                #     print(key, type(info["automatic_captions"][key]))
                # _info["upload_date"] = info["upload_date"]
                # info = _info
        if not info:
            raise ValueError
        return info
