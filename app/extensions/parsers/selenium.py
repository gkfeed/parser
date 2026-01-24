from datetime import timedelta
from abc import ABC

from selenium.webdriver.remote.webdriver import WebDriver

from app.services.cache.use_temporary import async_store_in_cache_for
from app.services.selenium import SeleniumService, SeleniumGetHtmlArgs
from .http import HttpParserExtension


class SeleniumParserExtension(HttpParserExtension, ABC):
    _http_response_storage_time = timedelta(hours=1)
    _selenium_wait_time = 0
    _should_delete_cookies = False
    _should_load_cookies = False
    _should_save_cookies = False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # @async_store_in_cache_for(_http_response_storage_time)
        # async def get_html(self, url: str) -> bytes:
        cls.get_html = async_store_in_cache_for(cls._http_response_storage_time)(
            cls.get_html
        )

    async def get_html(self, url: str) -> bytes:
        html = await SeleniumService.get_html(
            SeleniumGetHtmlArgs(
                url=url,
                should_delete_cookies=self._should_delete_cookies,
                should_load_cookies=self._should_load_cookies,
                should_save_cookies=self._should_save_cookies,
                make_actions_function=self.make_actions,
                selenium_wait_timeout_seconds=self._selenium_wait_time,
            )
        )
        return html.encode()

    def make_actions(self, driver: WebDriver):
        pass
