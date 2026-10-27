import re
from collections.abc import Callable
from typing import ClassVar, Literal, Never

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
    """Opt-in browser diagnostics configured with source selectors and hooks."""

    _results_wait_time = 30
    _diagnostic_event = "browser_source_unavailable"
    _diagnostic_selectors: ClassVar[dict[str, str]] = {}
    _diagnostic_visible_selectors: ClassVar[dict[str, str]] = {}
    _diagnostic_error_selector = ""
    _diagnostic_content_selector = ""

    def _wait_for[T](
        self,
        driver: WebDriver,
        stage: str,
        condition: Callable[[WebDriver], T | Literal[False]],
    ) -> T:
        try:
            return WebDriverWait(driver, self._results_wait_time).until(condition)
        except TimeoutException as exc:
            raise self._browser_unavailable(
                driver, stage, reason=f"{stage}_timeout"
            ) from exc

    def _check_error(self, driver: WebDriver, error: WebElement, stage: str) -> Never:
        raise self._browser_unavailable(
            driver, stage, message=error.get_attribute("textContent") or ""
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

    def _browser_unavailable(
        self,
        driver: WebDriver,
        stage: str,
        *,
        reason: str | None = None,
        message: str = "",
    ) -> FeedUnavailable:
        """Diagnose a browser failure without logging page text or credentials."""
        context: dict = {}
        try:
            context = driver.execute_script(
                """
                const [counts, visibleCounts, errorSelector, contentSelector] = arguments;
                const count = s => document.querySelectorAll(s).length;
                const countVisible = s => [...document.querySelectorAll(s)].filter(e =>
                    e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})).length;
                const contentPresent = contentSelector && document.querySelector(contentSelector);
                return {
                    ...Object.fromEntries(Object.entries(counts).map(([k, s]) => [k, count(s)])),
                    ...Object.fromEntries(Object.entries(visibleCounts).map(([k, s]) => [k, countVisible(s)])),
                    document_status: performance.getEntriesByType('navigation')[0]?.responseStatus || null,
                    source_message: errorSelector ?
                        document.querySelector(errorSelector)?.textContent || '' : '',
                    // Read full-page failures only when the expected UI is absent.
                    // These texts are classified and hashed, never logged.
                    page_message: !contentPresent ?
                        document.title + ' ' + (document.body?.innerText || '') : ''
                };
                """,
                self._diagnostic_selectors,
                self._diagnostic_visible_selectors,
                self._diagnostic_error_selector,
                self._diagnostic_content_selector,
            )
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
