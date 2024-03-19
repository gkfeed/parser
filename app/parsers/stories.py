from typing import AsyncGenerator
from urllib.parse import unquote
from datetime import timedelta

from app.utils.return_empty_when import async_return_empty_when
from app.serializers.feed import Item
from app.extentions.parsers.exceptions import UnavailableFeed
from app.extentions.parsers.http import HttpParserExtention
from app.extentions.parsers.cache import (
    CacheFeedExtention,
    async_store_in_cache_if_not_empty_for,
)
from app.utils.datetime import constant_datetime


class InstagramStoriesFeed(HttpParserExtention, CacheFeedExtention):
    __base_url = "https://ig.opnxng.com"

    @property
    @async_store_in_cache_if_not_empty_for(timedelta(days=1))
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
