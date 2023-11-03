import asyncio
from datetime import datetime

from app.utils.return_empty_when import async_return_empty_when
from app.utils.datetime import convert_datetime
from app.serializers.feed import Item
from app.extentions.parsers.selenium import SeleniumParserExtention
from ._base import BaseTikTokFeed


class TikTokSeleniumFeed(BaseTikTokFeed, SeleniumParserExtention):
    _selenium_wait_time = 2
    _should_load_cookies = True
    _should_save_cookies = True

    @property
    async def _video_links(self) -> list[str]:
        soup = await self.get_soup(self.feed.url)

        links = soup.find_all("a")

        video_links = []
        for link in links:
            try:
                if (href := link["href"]).startswith(self.feed.url):
                    video_links.append(href)
            except KeyError:
                continue

        return video_links
