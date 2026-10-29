from dataclasses import dataclass, field
from hashlib import sha256
from typing import final, override

import structlog
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from .selenium import SeleniumParserExtension

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class BrowserSnapshot:
    """Safe structured fields and separate text that is only hashed when logged."""

    fields: dict[str, object]
    text: str = field(default="", repr=False)


class SeleniumDiagnosticsExtension(SeleniumParserExtension):
    """Opt-in browser diagnostics with an optional source context hook."""

    _diagnostic_event = "browser_diagnostics"
    _driver: WebDriver | None = None

    @property
    def driver(self) -> WebDriver:
        """The driver is available only while browser actions are running."""
        if self._driver is None:
            raise RuntimeError("Browser actions are not active")
        return self._driver

    @final
    @override
    def make_actions(self, driver: WebDriver) -> None:
        if self._driver is not None:
            raise RuntimeError("Browser actions are already active")
        self._driver = driver
        try:
            self._make_actions()
        finally:
            self._driver = None

    def _make_actions(self) -> None:
        raise NotImplementedError("Implement browser actions using self.driver")

    def _click_element(self, element: WebElement) -> None:
        self._click(self.driver, element)

    def _browser_context(self) -> BrowserSnapshot:
        snapshot = self.driver.execute_script(
            """
            return {
                document_status: performance.getEntriesByType('navigation')[0]?.responseStatus || null,
                text: document.title + ' ' + (document.body?.innerText || '')
            };
            """
        )
        text = snapshot.pop("text", "")
        return BrowserSnapshot(snapshot, text=text)

    def _capture_browser_context(self) -> BrowserSnapshot:
        try:
            return self._browser_context()
        except WebDriverException as exc:
            # Snapshot failure must not replace the operation's actual error.
            return BrowserSnapshot({"diagnostic_error": type(exc).__name__})

    def _log_browser_diagnostics(
        self,
        stage: str,
        snapshot: BrowserSnapshot,
        *,
        message: str = "",
        **details: object,
    ) -> None:
        """Record observations without interpreting or changing the outcome."""
        text = message or snapshot.text
        logger.warning(
            self._diagnostic_event,
            stage=stage,
            message_length=len(text),
            message_hash=sha256(text.encode()).hexdigest() if text else None,
            **snapshot.fields,
            **details,
        )
