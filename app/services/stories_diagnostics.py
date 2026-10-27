import re

import structlog
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver

from app.services.hash import HashService

logger = structlog.get_logger(__name__)


def _error_http_status(message: str) -> int | None:
    # Only explicit HTTP/error syntax or standard status titles count.
    match = re.search(
        r"\b(?:http(?: error)?|status(?: code)?|error)\s*[:=-]?\s*([45]\d{2})\b"
        r"|\b([45]\d{2})\s+(?:bad gateway|service unavailable|forbidden|"
        r"too many requests|unauthorized|internal server error|gateway timeout)\b",
        message.lower(),
    )
    return int(match.group(1) or match.group(2)) if match else None


def classify_error(message: str) -> str:
    message = message.lower()
    if any(
        text in message
        for text in (
            "captcha",
            "verify you are human",
            "challenge-platform",
            "just a moment",
        )
    ):
        return "challenge_required"
    if any(
        text in message
        for text in (
            "log in",
            "login required",
            "sign in",
            "authentication required",
        )
    ):
        return "authentication_required"
    status = _error_http_status(message)
    if status == 401:
        return "authentication_required"
    if "too many requests" in message or status == 429:
        return "rate_limited"
    if status is not None:
        return "upstream_http_error"
    if any(
        text in message
        for text in (
            "bad gateway",
            "service unavailable",
            "internal server error",
            "<!doctype html",
            "<html",
        )
    ):
        return "upstream_error_page"
    if "no stories" in message:
        # The source also uses this message for upstream failures.
        return "empty_unverified"
    if "private" in message:
        return "private"
    if any(
        text in message
        for text in ("user not found", "profile not found", "account not found")
    ):
        return "not_found"
    return "upstream_error"


def log_browser_failure(
    driver: WebDriver, reason: str, stage: str, *, message: str = ""
) -> str:
    """Log safe source diagnostics and return the classified failure reason."""
    context: dict = {}
    try:
        context = driver.execute_script(
            """
            const count = s => document.querySelectorAll(s).length;
            const triggers = [...document.querySelectorAll(
                '.search-result .profile-media-list .trigger')];
            const forms = count('form.search-form');
            const results = count('.search-result');
            return {
                document_status: performance.getEntriesByType('navigation')[0]?.responseStatus || null,
                search_forms: forms,
                search_results: results,
                loaders: count('.search-result .loader-component'),
                media_cards: count('.search-result .profile-media-list__item'),
                download_links: count('.search-result a.download-btn[href]'),
                subscription_landings: count('.tz-landing-exp'),
                pagination_triggers: triggers.length,
                visible_pagination_triggers: triggers.filter(e =>
                    e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})).length,
                source_message: document.querySelector(
                    '.search-result .error-message__text')?.textContent || '',
                // Full-page failures have no search UI. Never log this text.
                page_message: !forms && !results ?
                    document.title + ' ' + (document.body?.innerText || '') : ''
            };
            """
        )
    except WebDriverException as exc:
        # Diagnostics must preserve the actual source failure.
        context["diagnostic_error"] = type(exc).__name__
    page_message = context.pop("page_message", "")
    source_message = context.pop("source_message", "")
    message = message or source_message or page_message
    error_kind = classify_error(message) if message else None
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
        "stories_source_unavailable",
        stage=stage,
        reason=reason,
        error_kind=error_kind,
        error_http_status=_error_http_status(message),
        message_length=len(message),
        message_hash=HashService.hash_str(message) if message else None,
        **context,
    )
    return reason
