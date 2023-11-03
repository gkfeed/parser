from datetime import timedelta
from abc import ABC
import time
import pickle
import os

from selenium import webdriver

from app.settings import SELENIUM_COOKIES_PATH
from app.services.cache.use_temporary import async_store_in_cache_for
from app.services.queue import async_run_sync_in_queue
from .http import HttpParserExtention


class SeleniumParserExtention(HttpParserExtention, ABC):
    _cache_storage_time = timedelta(hours=1)
    _selenium_wait_time = 0
    _should_load_cookies = False
    _should_save_cookies = False

    @async_store_in_cache_for(_cache_storage_time)
    @async_run_sync_in_queue
    def get_html(self, url: str) -> bytes:
        driver = webdriver.Remote(
            "http://10.5.0.5:4444",
            options=webdriver.ChromeOptions(),
        )
        try:
            if self._should_load_cookies:
                driver.get(url)
                driver.delete_all_cookies()
                for cookie in self._load_cookies():
                    driver.add_cookie(cookie)

            driver.get(url)
            time.sleep(self._selenium_wait_time)
            html = driver.page_source

            if self._should_save_cookies:
                pickle.dump(driver.get_cookies(), open(SELENIUM_COOKIES_PATH, "wb"))

            driver.close()
            driver.quit()
            return html
        except Exception as e:
            driver.close()
            driver.quit()
            raise e

    def _load_cookies(self):
        if not os.path.isfile(SELENIUM_COOKIES_PATH):
            return []
        return pickle.load(open(SELENIUM_COOKIES_PATH, "rb"))
