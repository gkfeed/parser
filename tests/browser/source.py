"""An example diagnostic consumer with its own operation and failure policy."""

from datetime import timedelta
from typing import override

from bs4 import Tag
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app.extensions.parsers.selenium_diagnostics import (
    BrowserSnapshot,
    SeleniumDiagnosticsExtension,
)
from app.serializers.feed import Feed, Item
from app.services.cache.storage.memory import MemoryStorage
from app.services.cache.temporary import TemporaryCacheService
from app.utils.datetime import constant_datetime
from tests.browser.resources import LocalChromium


class SourceFailure(ValueError):
    pass


class ObservedSource(SeleniumDiagnosticsExtension):
    _http_response_storage_time = timedelta(0)

    @override
    async def _parse_items(self) -> list[Item]:
        soup = await self.get_soup(self.feed.url)
        ready = soup.select_one("#ready")
        if not isinstance(ready, Tag):
            raise SourceFailure("Catalog operation failed")
        return [
            Item(
                title=ready.get_text(),
                text="",
                date=constant_datetime,
                link=self.feed.url,
            )
        ]

    @override
    def _make_actions(self) -> None:
        try:
            self._require_ready()
        except (SourceFailure, TimeoutException):
            if self.driver.find_elements(By.ID, "close-window"):
                self.driver.close()
            snapshot = self._capture_browser_context()
            self._log_browser_diagnostics(
                "catalog_ready", snapshot, snapshot_repr=repr(snapshot)
            )
            raise

    def _require_ready(self) -> None:
        if self.driver.find_elements(By.ID, "error"):
            raise SourceFailure("Catalog operation failed")
        WebDriverWait(self.driver, 0).until(
            EC.presence_of_element_located((By.ID, "ready"))
        )

    @override
    def _browser_context(self) -> BrowserSnapshot:
        snapshot = super()._browser_context()
        fields = self.driver.execute_script("""
            const entries = [...document.querySelectorAll('.entry')];
            return {
                entries: entries.length,
                visible_entries: entries.filter(e =>
                    e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})).length
            };
        """)
        return BrowserSnapshot({**snapshot.fields, **fields}, text=snapshot.text)


def source(url: str, browser: LocalChromium) -> ObservedSource:
    parser = ObservedSource(Feed(id=1, title="Local", type="catalog", url=url), {})
    parser.selenium_driver_factory = browser
    parser.cache = TemporaryCacheService(storage=MemoryStorage())
    return parser
