from datetime import timedelta
from typing import AsyncGenerator

from bs4 import Tag

from app.serializers.feed import Item
from app.utils.datetime import constant_datetime

from app.extensions.parsers.selenium import SeleniumParserExtension
from app.extensions.parsers.cache import CacheFeedExtension


class InstagramFeed(SeleniumParserExtension, CacheFeedExtension):
    __base_url = "https://www.piokok.com"
    _cache_storage_time_if_success = timedelta(days=1)
    _http_run_in_queue = True
    _selenium_wait_time = 60

    @property
    async def items(self) -> list[Item]:
        return [
            Item(
                title="inst: " + self._user_name,
                text=self._user_name,
                date=constant_datetime,
                link=self.__base_url + link,
            )
            async for link in self._posts_links
        ]

    async def get_post_photos_links(self, url: str) -> list[str]:
        soup = await self.get_soup(url)
        return [
            str(pic.a["href"])
            for pic in soup.find_all(class_="pic")
            if isinstance(pic, Tag) and pic.a and "href" in pic.a.attrs
        ]

    @property
    async def _posts_links(self) -> AsyncGenerator[str, str]:
        url = f"{self.__base_url}/profile/{self._user_name}"
        soup = await self.get_soup(url)
        for link_tag in soup.find_all("a", class_="cover_link"):
            if isinstance(link_tag, Tag) and "href" in link_tag.attrs:
                yield str(link_tag["href"])

    @property
    def _user_name(self) -> str:
        return self.feed.url.split("/")[-1]
