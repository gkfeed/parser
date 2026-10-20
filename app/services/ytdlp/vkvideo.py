from typing import Any, ClassVar, NotRequired, TypedDict, cast

from .extractor import YtdlpInfoExtractor
from .modes import BaseExtractionMode


class VkVideoChannelInfo(TypedDict):
    """Validated entries; optional source fields remain available to the parser."""

    title: NotRequired[Any]
    entries: list[dict[str, Any]]


class _InvalidVkVideoMetadata(ValueError):
    """The source returned metadata that cannot describe a video feed."""


def video_link(video: dict[str, Any]) -> str:
    video_id = video.get("id")
    if video_id:
        if not isinstance(video_id, (str, int)) or isinstance(video_id, bool):
            raise _InvalidVkVideoMetadata(
                "VK Video extraction returned an invalid video ID"
            )
        if not str(video_id).strip():
            raise _InvalidVkVideoMetadata(
                "VK Video extraction returned a blank video ID"
            )
        return f"https://vkvideo.ru/video{video_id}"

    link = video.get("webpage_url") or video.get("url")
    if not isinstance(link, str) or not link.strip():
        raise _InvalidVkVideoMetadata(
            "VK Video extraction returned a video without a usable link"
        )
    return link


def _validate_extraction(
    url: str, info: dict[str, Any] | None, error: str | None
) -> dict[str, Any]:
    if not isinstance(info, dict):
        raise _InvalidVkVideoMetadata("VK Video extraction did not return metadata")
    entries = info.get("entries")
    if not isinstance(entries, list):
        raise _InvalidVkVideoMetadata(
            "VK Video extraction did not return an entries list"
        )
    if not entries:
        # An empty extraction does not confirm that the channel has no videos.
        raise _InvalidVkVideoMetadata("VK Video extraction returned no videos")
    for video in entries:
        if not isinstance(video, dict) or not video:
            raise _InvalidVkVideoMetadata(
                "VK Video extraction returned an invalid video entry"
            )
        video_link(video)
    return info


class VkVideoExtractionMode(BaseExtractionMode):
    result_handler = staticmethod(_validate_extraction)
    opts: ClassVar[dict[str, Any]] = {
        **BaseExtractionMode.opts,
        "extract_flat": False,
        "skip_download": True,
    }


async def extract_channel_videos(url: str, max_videos: int) -> VkVideoChannelInfo:
    info = await YtdlpInfoExtractor.extract_channel_videos_info(
        url, VkVideoExtractionMode(), max_videos
    )
    # Cached results bypass the extraction mode's result handler.
    return cast(VkVideoChannelInfo, _validate_extraction(url, info, None))
