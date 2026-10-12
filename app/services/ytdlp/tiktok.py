from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from app.extensions.parsers.exceptions import FeedUnavailable

logger = structlog.get_logger(__name__)


class TikTokVideoRestricted(ValueError):
    """TikTok explicitly denied access to an individual video."""


def classify_video(
    url: str, info: dict[str, Any] | None, error: str | None
) -> dict[str, Any] | None:
    message = error or ""
    if any(
        reason in message
        for reason in (
            "You do not have permission to view this post",
            "TikTok is requiring login",
            "Video not available, status code 10216",
            "Video not available, status code 10222",
        )
    ):
        raise TikTokVideoRestricted(url)
    return info


def classify_profile(
    url: str, info: dict[str, Any] | None, error: str | None
) -> dict[str, Any]:
    message = error or ""
    if "This account does not have any videos posted" in message:
        logger.info("tiktok_profile_classified", outcome="empty_confirmed")
        return {"entries": [], "tiktok_outcome": "empty_confirmed"}

    if any(
        reason in message
        for reason in (
            "account is private",
            "account is likely either private",
            "all of their videos are private",
            "TikTok is requiring login",
        )
    ):
        retry_at = datetime.now(UTC) + timedelta(days=1)
        logger.warning("tiktok_profile_classified", outcome="restricted")
        raise FeedUnavailable(url, "tiktok_profile_restricted", retry_at)

    if "Unable to extract secondary user ID" in message:
        retry_at = datetime.now(UTC) + timedelta(hours=1)
        logger.warning("tiktok_profile_classified", outcome="unavailable")
        raise FeedUnavailable(url, "tiktok_profile_unavailable", retry_at)

    if info and info.get("entries") and error:
        logger.warning("tiktok_profile_classified", outcome="partial")
        return {**info, "tiktok_outcome": "partial", "extraction_incomplete": True}

    if info is None or error:
        logger.warning("tiktok_profile_classified", outcome="extraction_failed")
        raise FeedUnavailable(url, "tiktok_profile_extraction_failed")

    if info.get("entries") == []:
        logger.warning("tiktok_profile_classified", outcome="empty_unverified")
        raise FeedUnavailable(url, "tiktok_profile_empty_unverified")

    logger.info("tiktok_profile_classified", outcome="videos_found")
    return {**info, "tiktok_outcome": "videos_found"}
