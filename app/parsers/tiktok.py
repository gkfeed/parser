from datetime import datetime

from app.utils.datetime import convert_datetime
from app.serializers.feed import Item
from app.services.tiktok import TikTokInfoExtractor
from ._exceptions import UnavailableFeed
from ._base import BaseFeed


class TikTokFeed(BaseFeed):
    @property
    async def items(self) -> list[Item]:
        try:
            info = await TikTokInfoExtractor.get_page_info(self.feed.url)
            videos = info['entries']
            return [
                Item(
                    title=v['description'],
                    text=v['description'],
                    date=await self._get_video_publish_date(v),
                    link=self.feed.url + '/video/' +
                    v['webpage_url'].split('/')[-1],
                )
                for v in videos
            ]
        except (UnavailableFeed, ValueError):
            return []

    async def _get_video_publish_date(self, video: dict) -> datetime:
        date_str = datetime.fromtimestamp(
            video['timestamp']).strftime('%Y%m%d %H:%M:%S')
        return convert_datetime(date_str)
