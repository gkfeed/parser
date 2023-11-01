from datetime import datetime

from app.utils.datetime import convert_datetime
from app.utils.return_empty_when import async_return_empty_when
from app.serializers.feed import Item
from app.services.youtube import YoutubeInfoExtractor
from app.extentions.parsers.exceptions import UnavailableFeed
from app.extentions.parsers.base import BaseFeed


class YoutubeFeed(BaseFeed):
    @property
    @async_return_empty_when(UnavailableFeed, ValueError)
    async def items(self) -> list[Item]:
        videos_url = self.feed.url + "/videos"
        info = await YoutubeInfoExtractor.get_page_info(videos_url)
        channel_name = info["uploader"]
        videos = info["entries"]
        return [
            Item(
                title="YT: " + channel_name,
                text=v["title"],
                date=await self._get_video_publish_date(v),
                link=v["url"],
            )
            for v in videos
        ]

    async def _get_video_publish_date(self, video: dict) -> datetime:
        today_timestamp = datetime.today().timestamp()
        if video["timestamp"] and video["timestamp"] >= today_timestamp:
            date_str = datetime.fromtimestamp(video["timestamp"]).strftime("%Y%m%d")
            return convert_datetime(date_str)
        info = await YoutubeInfoExtractor.get_video_info(video["url"])
        return convert_datetime(info["upload_date"])
