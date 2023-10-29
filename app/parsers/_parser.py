from abc import ABC
from bs4 import BeautifulSoup
from datetime import timedelta
from selenium import webdriver

from app.services.cache.use_temporary import (
    UseTemporaryCacheServiceExtension,
    async_store_in_cache_for,
)
from app.services.http import HttpService, HttpRequestError
from app.services.queue import async_queue_wrap
from ._exceptions import UnavailableFeed
from ._base import BaseFeed as _BaseFeed


class WebParser(_BaseFeed, UseTemporaryCacheServiceExtension[bytes], ABC):
    _cache_storage_time = timedelta(minutes=5)

    @async_store_in_cache_for(_cache_storage_time)
    async def get_html(self, url: str) -> bytes:
        try:
            return await HttpService.get(url)
        except HttpRequestError:
            print("FAILED: " + self.feed.type + " : " + self.feed.title)
            raise UnavailableFeed(self.feed.url)

    async def get_soup(self, url: str) -> BeautifulSoup:
        return BeautifulSoup(await self.get_html(url), "html.parser")


class WebParserWithSelenium(WebParser, ABC):
    _cache_storage_time = timedelta(days=1)

    @async_store_in_cache_for(_cache_storage_time)
    @async_queue_wrap
    def get_html(self, url: str) -> bytes:
        driver = webdriver.Remote(
            "http://10.5.0.5:4444",
            options=webdriver.ChromeOptions(),
        )
        try:
            driver.get(url)
            html = driver.page_source
            driver.close()
            driver.quit()
            return html
        except Exception as e:
            driver.close()
            driver.quit()
            raise e
