from datetime import datetime
import asyncio

from app.utils.datetime import convert_datetime
from app.serializers.feed import Item
from app.services.tiktok import TikTokInfoExtractor
from app.extentions.parsers.base import BaseFeed
from app.extentions.parsers.exceptions import UnavailableFeed
from app.extentions.parsers.selenium import SeleniumParserExtention


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


class TikTokSeleniumFeed(SeleniumParserExtention):
    @property
    async def items(self) -> list[Item]:
        try:
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

            return items
        # BUG: if cant fetch one of video links return nothing
        except (UnavailableFeed, ValueError, TypeError, KeyError):
            return []

    async def _get_video_publish_date(self, video: dict) -> datetime:
        date_str = datetime.fromtimestamp(video["timestamp"]).strftime(
            "%Y%m%d %H:%M:%S"
        )
        return convert_datetime(date_str)
