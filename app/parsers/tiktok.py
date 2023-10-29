from datetime import datetime, timedelta
import asyncio

from app.utils.datetime import convert_datetime
from app.serializers.feed import Item
from app.services.cache.temporary import (
    TemporaryCacheService,
    UndefinedCache,
    ExpiredCache,
)
from app.services.cache.storage.memory import MemoryStorage
from app.services.tiktok import TikTokInfoExtractor
from ._exceptions import UnavailableFeed
from ._base import BaseFeed
from ._parser import WebParserWithSelenium


class TikTokFeed(BaseFeed):
    @property
    async def items(self) -> list[Item]:
        try:
            info = await TikTokInfoExtractor.get_page_info(self.feed.url)
            videos = info["entries"]
            return [
                Item(
                    title=v["description"],
                    text=v["description"],
                    date=await self._get_video_publish_date(v),
                    link=self.feed.url + "/video/" + v["webpage_url"].split("/")[-1],
                )
                for v in videos
            ]
        except (UnavailableFeed, ValueError, TypeError):
            return []

    async def _get_video_publish_date(self, video: dict) -> datetime:
        date_str = datetime.fromtimestamp(video["timestamp"]).strftime(
            "%Y%m%d %H:%M:%S"
        )
        return convert_datetime(date_str)


class TikTokSeleniumFeed(WebParserWithSelenium):
    __cache = TemporaryCacheService(MemoryStorage())

    @property
    async def items(self) -> list[Item]:
        try:
            try:
                soup = self.__cache.get(self.feed.url)
            except (UndefinedCache, ExpiredCache):
                soup = await self.get_soup(self.feed.url)

            links = soup.find_all("a")

            video_links = []
            for link in links:
                try:
                    if (href := link["href"]).startswith(self.feed.url):
                        video_links.append(href)
                except KeyError:
                    continue

            tasks = []
            async with asyncio.TaskGroup() as tg:
                for link in video_links:
                    tasks.append(
                        tg.create_task(TikTokInfoExtractor.get_video_info(link))
                    )

            items = []
            for task in tasks:
                info = task.result()
                items.append(
                    Item(
                        title=info["description"],
                        text=info["description"],
                        date=await self._get_video_publish_date(info),
                        link=self.feed.url
                        + "/video/"
                        + info["webpage_url"].split("/")[-1],
                    )
                )

            if items:
                self.__cache.set(self.feed.url, soup, timedelta(days=1))

            return items
        except (UnavailableFeed, ValueError, TypeError):
            return []

    async def _get_video_publish_date(self, video: dict) -> datetime:
        date_str = datetime.fromtimestamp(video["timestamp"]).strftime(
            "%Y%m%d %H:%M:%S"
        )
        return convert_datetime(date_str)
