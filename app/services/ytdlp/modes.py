from typing import Any, ClassVar


class BaseExtractionMode:
    opts: ClassVar[dict[str, Any]] = {
        "socket_timeout": 60,
        "ignoreerrors": True,
        "quiet": True,
        "lazy_playlist": False,
        "extract_flat": True,
    }


class ChannelExtractionMode(BaseExtractionMode):
    max_videos = 5
    opts: ClassVar[dict[str, Any]] = {
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
