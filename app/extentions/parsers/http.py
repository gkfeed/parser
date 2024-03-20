from abc import ABC
from bs4 import BeautifulSoup
from datetime import timedelta

from app.services.http import HttpService, HttpRequestError
from app.services.cache.use_temporary import (
    UseTemporaryCacheServiceExtension,
    async_store_in_cache_for,
)
from .exceptions import UnavailableFeed
from .base import BaseFeed as _BaseFeed


# NOTE: do not inherit of BaseFeed
class HttpParserExtention(_BaseFeed, UseTemporaryCacheServiceExtension[bytes], ABC):
    _http_repsponse_storage_time = timedelta(minutes=5)
    _headers = HttpService.headers

    @async_store_in_cache_for(_http_repsponse_storage_time)
    async def get_html(self, url: str) -> bytes:
        try:
            return await HttpService.get(url, headers=self._headers)
        except HttpRequestError:
            raise UnavailableFeed(self.feed.url)

    async def get_soup(self, url: str) -> BeautifulSoup:
        return BeautifulSoup(await self.get_html(url), "html.parser")
