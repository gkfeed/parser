from typing import Any, ClassVar


class BaseExtractionMode:
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
