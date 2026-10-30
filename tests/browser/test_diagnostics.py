import json
from datetime import timedelta
from hashlib import sha256
from typing import override

import pytest
from bs4 import Tag
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from structlog.testing import capture_logs

from app.extensions.parsers.selenium_diagnostics import (
    BrowserSnapshot,
    SeleniumDiagnosticsExtension,
)
from app.serializers.feed import Feed, Item
from app.services.cache.storage.memory import MemoryStorage
from app.services.cache.temporary import TemporaryCacheService
from app.utils.datetime import constant_datetime
from tests.browser.resources import LocalChromium

pytestmark = pytest.mark.integration


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


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (200, "This account is private"),
        (403, "Verify you are human"),
        (429, "Too many requests"),
        (503, "Service unavailable"),
    ],
)
async def test_observations_preserve_the_consumers_error(
    site, browser, status, message
):
    url = site.publish(
        '<i class="entry"></i><i class="entry" hidden></i>'
        f'<div id="error">{message}</div>',
        status=status,
    )
    parser = source(url, browser)

    with capture_logs() as logs, pytest.raises(SourceFailure) as raised:
        await parser.items

    assert raised.value.args == ("Catalog operation failed",)
    assert len(logs) == 1
    event = logs[0]
    assert event["event"] == "browser_diagnostics"
    assert event["document_status"] == status
    assert event["stage"] == "catalog_ready"
    assert event["entries"] == 2
    assert event["visible_entries"] == 1
    assert "reason" not in event
    assert "error_kind" not in event
    browser.assert_released()


async def test_diagnostics_preserve_the_consumers_successful_item(site, browser):
    url = site.publish('<div id="ready">Loaded</div>')
    parser = source(url, browser)

    with capture_logs() as logs:
        items = await parser.items

    assert len(items) == 1
    assert items[0].title == "Loaded"
    assert items[0].link == url
    assert logs == []
    browser.assert_released()


async def test_closed_window_diagnostics_preserve_the_original_failure(site, browser):
    parser = source(
        site.publish('<div id="error"></div><i id="close-window"></i>'), browser
    )

    with capture_logs() as logs, pytest.raises(SourceFailure) as raised:
        await parser.items

    assert raised.value.args == ("Catalog operation failed",)
    assert logs[0]["diagnostic_error"] in {
        "NoSuchWindowException",
        "InvalidSessionIdException",
    }
    assert "reason" not in logs[0]
    assert "error_kind" not in logs[0]
    browser.assert_released()


async def test_snapshot_text_is_hashed_without_leaking_credentials(site, browser):
    secret_url = site.url + "/?token=SECRET_MARKER"
    site.publish(f'<div id="error">Failed {secret_url} &lt;html&gt;</div>')
    parser = source(secret_url, browser)

    with capture_logs() as logs, pytest.raises(SourceFailure):
        await parser.items

    assert len(logs) == 1
    expected_text = f" Failed {secret_url} <html>"
    assert logs[0]["message_hash"] == sha256(expected_text.encode()).hexdigest()
    assert "BrowserSnapshot" in logs[0]["snapshot_repr"]
    assert logs[0]["message_length"] > 0
    serialized = json.dumps(logs)
    for forbidden in ("SECRET_MARKER", "<html", "&lt;html", "token=", site.url):
        assert forbidden not in serialized
    assert "/?token=SECRET_MARKER" in site.requests
    browser.assert_released()
