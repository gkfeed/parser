from abc import ABC
from bs4 import BeautifulSoup
from datetime import timedelta

from app.services.cache.use_temporary import (
    UseTemporaryCacheServiceExtension, async_store_in_cache_for)
from app.services.http import HttpService, HttpRequestError
from ._exceptions import UnavailableFeed
from ._base import BaseFeed as _BaseFeed


class WebParser(_BaseFeed, UseTemporaryCacheServiceExtension[bytes], ABC):
    _cache_storage_time = timedelta(minutes=5)

    @async_store_in_cache_for(_cache_storage_time)
    async def get_html(self, url: str) -> bytes:
        try:
            return await HttpService.get(url)
        except HttpRequestError:
            print('FAILED: ' + self.feed.type + ' : ' + self.feed.title)
            raise UnavailableFeed(self.feed.url)

    async def get_soup(self, url: str) -> BeautifulSoup:
        return BeautifulSoup(await self.get_html(url), 'html.parser')
