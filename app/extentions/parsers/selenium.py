from datetime import timedelta
from abc import ABC

from selenium import webdriver

from app.services.cache.use_temporary import async_store_in_cache_for
from app.services.queue import async_queue_wrap
from .http import HttpParserExtention


class SeleniumParserExtention(HttpParserExtention, ABC):
    _cache_storage_time = timedelta(hours=1)

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
