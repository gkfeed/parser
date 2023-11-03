from datetime import timedelta
from abc import ABC
import time
import pickle

from selenium import webdriver

from app.services.cache.use_temporary import async_store_in_cache_for
from app.services.queue import async_run_sync_in_queue
from .http import HttpParserExtention


class SeleniumParserExtention(HttpParserExtention, ABC):
    __cookies = None
    _cache_storage_time = timedelta(hours=1)
    _selenium_wait_time = 0

    @async_store_in_cache_for(_cache_storage_time)
    @async_run_sync_in_queue
    def get_html(self, url: str) -> bytes:
        driver = webdriver.Remote(
            "http://10.5.0.5:4444",
            options=webdriver.ChromeOptions(),
        )
        try:
            if self.__cookies:
                for cookie in self.cookies:
                    driver.add_cookie(cookie)
            driver.get(url)
            time.sleep(self._selenium_wait_time)
            html = driver.page_source
            self.__cookies = driver.get_cookies()
            driver.close()
            driver.quit()
            return html
        except Exception as e:
            driver.close()
            driver.quit()
            raise e
