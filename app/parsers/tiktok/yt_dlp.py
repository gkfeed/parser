from datetime import datetime

from app.utils.datetime import convert_datetime
from app.services.tiktok import TikTokInfoExtractor
from ._base import BaseTikTokFeed


class TikTokFeed(BaseTikTokFeed):
    @property
    async def _video_links(self) -> list[str]:
        info = await TikTokInfoExtractor.get_info(self.feed.url)
        videos = info["entries"]
        return [
            self.feed.url + "/video/" + v["webpage_url"].split("/")[-1] for v in videos
        ]

    async def _get_video_publish_date(self, video: dict) -> datetime:
        date_str = datetime.fromtimestamp(video["timestamp"]).strftime(
            "%Y%m%d %H:%M:%S"
        )
        return convert_datetime(date_str)
