from datetime import datetime

from app.utils.datetime import convert_datetime

from app.services.ytdlp.extractor import YtdlpInfoExtractor
from app.services.ytdlp.modes import BaseExtractionMode
from ._base import BaseTikTokFeed


class TikTokFeed(BaseTikTokFeed):
    _max_videos = 5

    @property
    async def _video_links(self) -> list[str]:
        return await YtdlpInfoExtractor.extract_video_urls(
            self.feed.url, BaseExtractionMode(), self._max_videos
        )

    async def _get_video_publish_date(self, timestamp: float) -> datetime:
        date_str = datetime.fromtimestamp(timestamp).strftime("%Y%m%d %H:%M:%S")
        return convert_datetime(date_str)
