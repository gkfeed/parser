from abc import ABC
from datetime import timedelta
from typing import ClassVar

from bs4 import BeautifulSoup

from app.services.cache.use_temporary import (
    UseTemporaryCacheServiceExtension,
)
from app.services.http import HttpRequestError, HttpService

from .base import BaseFeed as _BaseFeed
from .exceptions import FeedUnavailable


async def http_get_in_queue(url: str, headers: dict) -> bytes:
    return await HttpService.get(url, headers=headers)


# NOTE: do not inherit of BaseFeed
class HttpParserExtension(_BaseFeed, UseTemporaryCacheServiceExtension[bytes], ABC):
    _http_response_storage_time = timedelta(minutes=5)
    _headers: ClassVar[dict[str, str]] = HttpService.headers
    # NOTE: deprecated use heavy worker instead
    _http_run_in_queue = False

    async def get_html(self, url: str) -> bytes:
        if self.cache.has_valid_cache(url):
            html = self.cache.get(url)
            try:
                self._validate_html(url, html)
            except (FeedUnavailable, ValueError):
                # Refresh invalid pages cached before validation was added.
                self.cache.set_with_expiry(url, html, timedelta(0))
            else:
                return html

        html = await self._fetch_html(url)
        self._validate_html(url, html)
        self.cache.set_with_expiry(url, html, self._http_response_storage_time)
        return html

    def _validate_html(self, url: str, html: bytes) -> None:
        """Raise FeedUnavailable or ValueError for an unusable page."""

    async def _fetch_html(self, url: str) -> bytes:
        try:
            if self._http_run_in_queue:
                return await http_get_in_queue(url, self._headers)
            return await HttpService.get(url, headers=self._headers)
        except HttpRequestError as exc:
            raise FeedUnavailable(self.feed.url, "http_request_failed") from exc

    async def get_soup(self, url: str) -> BeautifulSoup:
        return BeautifulSoup(await self.get_html(url), "html.parser")
