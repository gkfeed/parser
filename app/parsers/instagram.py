from typing import AsyncGenerator

from app.utils.return_empty_when import async_return_empty_when
from app.serializers.feed import Item
from app.extentions.parsers.exceptions import UnavailableFeed
from app.extentions.parsers.http import HttpParserExtention
from app.utils.datetime import constant_datetime


class InstagramFeed(HttpParserExtention):
    __base_url = "https://ig.opnxng.com"

    @property
    @async_return_empty_when(UnavailableFeed, ValueError, KeyError)
    async def items(self) -> list[Item]:
        return [
            Item(
                title="inst: " + self._user_name,
                text=self._user_name,
                date=constant_datetime,
                link="https://www.instagram.com" + link,
            )
            async for link in self._posts_links
        ]

    @property
    async def _posts_links(self) -> AsyncGenerator[str, str]:
        url = f"{self.__base_url}/{self._user_name}"
        soup = await self.get_soup(url)
        for link in soup.find_all("a"):
            if link["href"].startswith("/p/"):
                yield link["href"]

    @property
    def _user_name(self) -> str:
        return self.feed.url.split("/")[-1]
