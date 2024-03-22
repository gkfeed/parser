from typing import NamedTuple

from app.services.youtube import (
    YoutubeInfoExtractor,
    BaseExtractionMode,
    VideoExtractionMode,
)
from . import worker


class VideoInfo(NamedTuple):
    title: str
    upload_date_str: str
    channel_name: str


@worker
async def extract_video_urls(
    videos_url: str, extraction_mode: BaseExtractionMode, max_videos: int
) -> list[str]:
    info = await YoutubeInfoExtractor.get_info(videos_url, extraction_mode)
    return [v["url"] for v in info["entries"][-max_videos:]]


@worker
async def extract_video_info(url: str) -> VideoInfo:
    info = await YoutubeInfoExtractor.get_info(url, VideoExtractionMode())
    return VideoInfo(info["title"], info["upload_date"], info["uploader"])
