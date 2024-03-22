from typing import NamedTuple

from app.services.tiktok import TikTokInfoExtractor
from . import worker


class VideoInfo(NamedTuple):
    description: str
    url: str
    timestamp: float


@worker
async def extract_video_links(url: str) -> list[str]:
    info = await TikTokInfoExtractor.get_info(url, keys=["entries"])
    videos = info["entries"]
    return [url + "/video/" + v["webpage_url"].split("/")[-1] for v in videos]


@worker
async def extract_video_info(url: str) -> VideoInfo:
    info = await TikTokInfoExtractor.get_info(url)
    return VideoInfo(info["description"], info["webpage_url"], info["timestamp"])
