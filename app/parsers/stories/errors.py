import re
from datetime import UTC, datetime, timedelta

from app.extensions.parsers.exceptions import FeedUnavailable


def http_error_status(message: str) -> int | None:
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
    if re.search(
        r"captcha|verify you are human|challenge-platform|just a moment", message
    ):
        return "challenge_required"
    if re.search(r"log in|login required|sign in|authentication required", message):
        return "authentication_required"
    status = http_error_status(message)
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


def failure_reason(
    fallback: str | None,
    *,
    error_kind: str | None,
    document_status: object,
    full_page_error: bool,
) -> str:
    if error_kind in ("challenge_required", "authentication_required"):
        return error_kind
    if document_status == 401:
        return "authentication_required"
    if isinstance(document_status, int) and document_status >= 400:
        return "rate_limited" if document_status == 429 else "upstream_http_error"
    if full_page_error and error_kind in (
        "rate_limited",
        "upstream_http_error",
        "upstream_error_page",
    ):
        return error_kind
    return fallback or error_kind or "upstream_error"


def unavailable(feed_url: str, reason: str) -> FeedUnavailable:
    delay = (
        timedelta(days=1)
        if reason in ("private", "not_found")
        else timedelta(minutes=1)
    )
    return FeedUnavailable(feed_url, reason, datetime.now(UTC) + delay)
