from datetime import timedelta
from abc import ABC

from selenium.webdriver.remote.webdriver import WebDriver

from app.services.cache.use_temporary import async_store_in_cache_for
from app.workers.selenium import get_html, SeleniumGetHtmlArgs
from .http import HttpParserExtention


class SeleniumParserExtention(HttpParserExtention, ABC):
    _http_repsponse_storage_time = timedelta(hours=1)
    _selenium_wait_time = 0
    _should_delete_cookies = False
    _should_load_cookies = False
    _should_save_cookies = False

    @async_store_in_cache_for(_http_repsponse_storage_time)
    async def get_html(self, url: str) -> bytes:
        return await get_html(
            SeleniumGetHtmlArgs(
                url=url,
                should_delete_cookies=self._should_delete_cookies,
                should_load_cookies=self._should_load_cookies,
                should_save_cookies=self._should_save_cookies,
                make_actions_function=self.make_actions,
                selenium_wait_timeout_seconds=self._selenium_wait_time,
            )
        )

    def make_actions(self, driver: WebDriver):
        pass
