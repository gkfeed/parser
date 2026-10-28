import re
from collections.abc import Callable
from typing import Literal, Never, final, override

import structlog
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

from app.services.hash import HashService

from .exceptions import FeedUnavailable
from .selenium import SeleniumParserExtension

logger = structlog.get_logger(__name__)


class SeleniumDiagnosticsExtension(SeleniumParserExtension):
    """Opt-in browser diagnostics with an optional source context hook."""

    _results_wait_time = 30
    _diagnostic_event = "browser_source_unavailable"
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

    def _wait_for[T](
        self,
        stage: str,
        condition: Callable[[WebDriver], T | Literal[False]],
    ) -> T:
        try:
            return WebDriverWait(self.driver, self._results_wait_time).until(condition)
        except TimeoutException as exc:
            raise self._browser_unavailable(stage, reason=f"{stage}_timeout") from exc

    def _check_error(self, error: WebElement, stage: str) -> Never:
        raise self._browser_unavailable(
            stage, message=error.get_attribute("textContent") or ""
        )

    @staticmethod
    def _error_http_status(message: str) -> int | None:
        # Only explicit HTTP/error syntax or standard status titles count.
        match = re.search(
            r"\b(?:http(?: error)?|status(?: code)?|error)\s*[:=-]?\s*([45]\d{2})\b"
            r"|\b([45]\d{2})\s+(?:bad gateway|service unavailable|forbidden|"
            r"too many requests|unauthorized|internal server error|gateway timeout)\b",
            message.lower(),
        )
        return int(match.group(1) or match.group(2)) if match else None

    @classmethod
    def _classify_browser_error(cls, message: str) -> str:
        message = message.lower()
        if re.search(
            r"captcha|verify you are human|challenge-platform|just a moment", message
        ):
            return "challenge_required"
        if re.search(r"log in|login required|sign in|authentication required", message):
            return "authentication_required"
        status = cls._error_http_status(message)
        if status == 401:
            return "authentication_required"
        if "too many requests" in message or status == 429:
            return "rate_limited"
        if status is not None:
            return "upstream_http_error"
        if re.search(
            r"bad gateway|service unavailable|internal server error|<!doctype html|<html",
            message,
        ):
            return "upstream_error_page"
        return "upstream_error"

    def _browser_context(self) -> dict:
        """Return safe log fields; source_message/page_message are hashed, not logged."""
        return self.driver.execute_script(
            """
            return {
                document_status: performance.getEntriesByType('navigation')[0]?.responseStatus || null,
                page_message: document.title + ' ' + (document.body?.innerText || '')
            };
            """
        )

    def _browser_unavailable(
        self,
        stage: str,
        *,
        reason: str | None = None,
        message: str = "",
    ) -> FeedUnavailable:
        """Diagnose a browser failure without logging page text or credentials."""
        context: dict = {}
        try:
            context = self._browser_context()
        except WebDriverException as exc:
            # Diagnostics must preserve the actual source failure.
            context["diagnostic_error"] = type(exc).__name__
        page_message = context.pop("page_message", "")
        source_message = context.pop("source_message", "")
        message = message or source_message or page_message
        error_kind = self._classify_browser_error(message) if message else None
        reason = reason or error_kind or "upstream_error"
        document_status = context.get("document_status")
        if error_kind in ("challenge_required", "authentication_required"):
            reason = error_kind
        elif document_status == 401:
            reason = "authentication_required"
        elif isinstance(document_status, int) and document_status >= 400:
            reason = "rate_limited" if document_status == 429 else "upstream_http_error"
        elif page_message and error_kind in (
            "rate_limited",
            "upstream_http_error",
            "upstream_error_page",
        ):
            reason = error_kind
        logger.warning(
            self._diagnostic_event,
            stage=stage,
            reason=reason,
            error_kind=error_kind,
            error_http_status=self._error_http_status(message),
            message_length=len(message),
            message_hash=HashService.hash_str(message) if message else None,
            **context,
        )
        return self._unavailable(reason)

    def _unavailable(self, reason: str) -> FeedUnavailable:
        return FeedUnavailable(self.feed.url, reason)
