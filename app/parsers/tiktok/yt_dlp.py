from datetime import datetime

from app.utils.datetime import convert_datetime

from app.services.ytdlp.extractor import YtdlpInfoExtractor
from app.services.ytdlp.modes import BaseExtractionMode
from ._base import BaseTikTokFeed


class TikTokFeed(BaseTikTokFeed):
    _max_videos = 5

    @property
    async def _video_links(self) -> list[str]:
        # NOTE: it s actually max videos fetched by ytdlp extractor
        info = await YtdlpInfoExtractor.extract_channel_videos_info(
            self.feed.url, BaseExtractionMode(), 0
        )

        videos = []
        for v in info["entries"]:
            if len(videos) >= self._max_videos:
                break
            if "url" not in v:
                continue
            videos.append(v["url"])
        return videos

    async def _get_video_publish_date(self, timestamp: float) -> datetime:
        date_str = datetime.fromtimestamp(timestamp).strftime("%Y%m%d %H:%M:%S")
        return convert_datetime(date_str)
