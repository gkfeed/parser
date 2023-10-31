from datetime import timedelta
from abc import ABC
import time

from selenium import webdriver

from app.services.cache.use_temporary import async_store_in_cache_for
from app.services.queue import async_run_sync_in_queue
from .http import HttpParserExtention


class SeleniumParserExtention(HttpParserExtention, ABC):
    _cache_storage_time = timedelta(hours=1)

    @async_store_in_cache_for(_cache_storage_time)
    @async_run_sync_in_queue
    def get_html(self, url: str) -> bytes:
        driver = webdriver.Remote(
            "http://10.5.0.5:4444",
            options=webdriver.ChromeOptions(),
        )
        try:
            driver.get(url)
            time.sleep(10)
            html = driver.page_source
            driver.close()
            driver.quit()
            return html
        except Exception as e:
            driver.close()
            driver.quit()
            raise e
