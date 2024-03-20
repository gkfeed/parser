from typing import AsyncGenerator
from urllib.parse import unquote
from datetime import timedelta

from app.serializers.feed import Item
from app.extentions.parsers.http import HttpParserExtention
from app.extentions.parsers.cache import CacheFeedExtention
from app.utils.datetime import constant_datetime


class InstagramStoriesFeed(HttpParserExtention, CacheFeedExtention):
    __base_url = "https://ig.opnxng.com"
    _cache_storage_time_if_success = timedelta(days=1)

    @property
    async def items(self) -> list[Item]:
        return [
            Item(
                title="inst: " + self._user_name,
                text=self._user_name,
                date=constant_datetime,
                link=link,
            )
            async for link in self._videos_links
        ]

    @property
    async def _videos_links(self) -> AsyncGenerator[str, str]:
        url = f"{self.__base_url}/{self._user_name}/stories"
        soup = await self.get_soup(url)
        for video in soup.find_all("video"):
            yield video["src"]
        for img in soup.find_all("img")[1:]:
            yield img["src"]

    @property
    def _user_name(self) -> str:
        return self.feed.url.split("/")[-1]

    def _extract_sublink(self, url: str) -> str:
        return unquote(url.split("?")[1][4:])
