import re

import structlog

from app.extensions.parsers.exceptions import FeedUnavailable
from app.services.http import HttpResponse
from app.utils.logging import url_log_fields

logger = structlog.get_logger(__name__)
_BODY_SCAN_BYTES = 65536


def http_unavailable(url: str, response: HttpResponse) -> FeedUnavailable:
    """Describe observed denial signals without logging bodies or raw headers."""
    markers = _block_markers(response) if response.status == 403 else []
    reason = f"http_status_{response.status}"
    if response.status == 403:
        reason = _forbidden_reason(markers)

    media_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    if not re.fullmatch(r"[a-z0-9!#$&^_.+-]{1,64}/[a-z0-9!#$&^_.+-]{1,64}", media_type):
        media_type = "unknown"
    logger.warning(
        "rss_http_unavailable",
        reason=reason,
        http_status=response.status,
        content_type=media_type,
        redirect_count=len(response.redirect_statuses),
        redirect_statuses=list(response.redirect_statuses),
        block_markers=markers,
        **url_log_fields(url),
        **url_log_fields(response.url or url, field="final_url"),
    )
    return FeedUnavailable(url, reason)


def _block_markers(response: HttpResponse) -> list[str]:
    body = response.content[:_BODY_SCAN_BYTES].decode("utf-8", errors="replace").lower()
    signals = {
        "cloudflare_challenge_header": (
            response.headers.get("cf-mitigated", "").lower() == "challenge"
        ),
        "cloudflare_challenge_page": (
            "/cdn-cgi/challenge-platform/" in body or "cf-chl-" in body
        ),
        "hosting_suspended_page": any(
            marker in body
            for marker in (
                "работа сайта приостановлена",
                "website is suspended",
                "account suspended",
            )
        ),
        "www_authenticate": bool(response.headers.get("www-authenticate")),
    }
    return [name for name, present in signals.items() if present]


def _forbidden_reason(markers: list[str]) -> str:
    if (
        "cloudflare_challenge_header" in markers
        or "cloudflare_challenge_page" in markers
    ):
        return "http_status_403_cloudflare_challenge"
    if "hosting_suspended_page" in markers:
        return "http_status_403_hosting_suspended"
    if "www_authenticate" in markers:
        return "http_status_403_auth_required"
    return "http_status_403"
