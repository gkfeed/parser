from datetime import datetime

from app.utils.datetime import convert_datetime
from app.workers.tiktok import extract_video_links
from ._base import BaseTikTokFeed


class TikTokFeed(BaseTikTokFeed):
    @property
    async def _video_links(self) -> list[str]:
        return await extract_video_links(self.feed.url)

    async def _get_video_publish_date(self, video: dict) -> datetime:
        date_str = datetime.fromtimestamp(video["timestamp"]).strftime(
            "%Y%m%d %H:%M:%S"
        )
        return convert_datetime(date_str)
