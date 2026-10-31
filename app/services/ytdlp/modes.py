from typing import Any, ClassVar

from yt_dlp.extractor.common import InfoExtractor

from app.services.ytdlp.tiktok import TikTokUserIE, classify_profile, classify_video
from app.workers.youtube import InfoResultHandler


class BaseExtractionMode:
    result_handler: InfoResultHandler | None = None
    extractor_class: ClassVar[type[InfoExtractor] | None] = None
    opts: ClassVar[dict[str, Any]] = {
        "socket_timeout": 60,
        "ignoreerrors": True,
        "quiet": True,
        "lazy_playlist": False,
        "extract_flat": True,
    }

    def options(self, max_videos: int | None = None) -> dict[str, Any]:
        options = self.opts.copy()
        if max_videos is not None:
            options["playlist_items"] = f"1-{max_videos}"
        return options


class ChannelExtractionMode(BaseExtractionMode):
    opts: ClassVar[dict[str, Any]] = {
        "socket_timeout": 60,
        "ignoreerrors": True,
        "quiet": True,
        "lazy_playlist": False,
        "extract_flat": True,
        "extractor_args": {
            "youtubetab": {
                "approximate_date": "upload_date",
            }
        },
    }


class TikTokProfileExtractionMode(BaseExtractionMode):
    result_handler = staticmethod(classify_profile)
    extractor_class = TikTokUserIE


class TikTokVideoExtractionMode(BaseExtractionMode):
    result_handler = staticmethod(classify_video)
    opts: ClassVar[dict[str, Any]] = {
        **BaseExtractionMode.opts,
        "ignore_no_formats_error": True,
    }


class VideoExtractionMode(BaseExtractionMode):
    opts: ClassVar[dict[str, Any]] = {
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
    opts: ClassVar[dict[str, Any]] = {
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
