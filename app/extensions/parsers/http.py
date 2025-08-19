from abc import ABC
from bs4 import BeautifulSoup
from datetime import timedelta

from app.workers import worker
from app.services.http import HttpService, HttpRequestError
from app.services.cache.use_temporary import (
    UseTemporaryCacheServiceExtension,
    async_store_in_cache_for,
)
from .exceptions import UnavailableFeed
from .base import BaseFeed as _BaseFeed


@worker
async def http_get_in_queue(url: str, headers: dict) -> bytes:
    return await HttpService.get(url, headers=headers)


# NOTE: do not inherit of BaseFeed
class HttpParserExtension(_BaseFeed, UseTemporaryCacheServiceExtension[bytes], ABC):
    _http_response_storage_time = timedelta(minutes=5)
    _headers = HttpService.headers
    _http_run_in_queue = False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # @async_store_in_cache_for(_http_response_storage_time)
        # async def get_html(self, url: str) -> bytes:
        cls.get_html = async_store_in_cache_for(cls._http_response_storage_time)(
            cls.get_html
        )

    async def get_html(self, url: str) -> bytes:
        try:
            if self._http_run_in_queue:
                return await http_get_in_queue(url, self._headers)
            return await HttpService.get(url, headers=self._headers)
        except HttpRequestError:
            raise UnavailableFeed(self.feed.url)

    async def get_soup(self, url: str) -> BeautifulSoup:
        return BeautifulSoup(await self.get_html(url), "html.parser")
