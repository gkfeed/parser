from abc import ABC
from datetime import timedelta

from selenium.webdriver.remote.webdriver import WebDriver

from app.core.worker_kind import WorkerKind
from app.services.selenium import SeleniumGetHtmlArgs, SeleniumService

from .http import HttpParserExtension


class SeleniumParserExtension(HttpParserExtension, ABC):
    worker_kind = WorkerKind.HEAVY
    _http_response_storage_time = timedelta(hours=1)
    _selenium_wait_time = 0
    _should_delete_cookies = False
    _should_load_cookies = False
    _should_save_cookies = False
    _page_load_timeout_seconds: int | None = None

    async def _fetch_html(self, url: str) -> bytes:
        html = await SeleniumService.get_html(
            SeleniumGetHtmlArgs(
                url=url,
                should_delete_cookies=self._should_delete_cookies,
                should_load_cookies=self._should_load_cookies,
                should_save_cookies=self._should_save_cookies,
                make_actions_function=self.make_actions,
                selenium_wait_timeout_seconds=self._selenium_wait_time,
                page_load_timeout_seconds=self._page_load_timeout_seconds,
            )
        )
        return html.encode()

    def make_actions(self, driver: WebDriver):
        pass
