from datetime import timedelta
from typing import AsyncGenerator

from app.serializers.feed import Item
from app.utils.datetime import constant_datetime
from app.extentions.parsers.http import HttpParserExtention
from app.extentions.parsers.cache import CacheFeedExtention


class InstagramFeed(HttpParserExtention, CacheFeedExtention):
    __base_url = "https://www.piokok.com"
    _cache_storage_time_if_success = timedelta(days=1)

    @property
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
        url = f"{self.__base_url}/profile/{self._user_name}"
        soup = await self.get_soup(url)
        for link in soup.find_all("a", class_="cover_link"):
            yield link["href"]

    @property
    def _user_name(self) -> str:
        return self.feed.url.split("/")[-1]
