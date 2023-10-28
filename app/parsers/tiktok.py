from datetime import datetime

import yt_dlp

from app.utils.datetime import convert_datetime
from app.serializers.feed import Item
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

            items = []
            for link in video_links:
                with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
                    info = ydl.extract_info(link, download=False)
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
        except (UnavailableFeed, ValueError, TypeError):
            return []

    async def _get_video_publish_date(self, video: dict) -> datetime:
        date_str = datetime.fromtimestamp(video["timestamp"]).strftime(
            "%Y%m%d %H:%M:%S"
        )
        return convert_datetime(date_str)
