from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from yt_dlp.extractor.tiktok import TikTokUserIE as UpstreamTikTokUserIE
from yt_dlp.utils import ExtractorError

from app.extensions.parsers.exceptions import FeedUnavailable

logger = structlog.get_logger(__name__)


class TikTokUserIE(UpstreamTikTokUserIE):
    """Keep the upstream extractor key and handle explicit profile denials."""

    def _get_universal_data(self, webpage: str, display_id: str) -> dict[str, Any]:
        data = super()._get_universal_data(webpage, display_id)
        if not isinstance(data, dict):
            raise TypeError("TikTok profile data is not an object")
        detail = data.get("webapp.user-detail")
        if not isinstance(detail, dict):
            return data

        status = detail.get("statusCode")
        logger.info(
            "tiktok_profile_response",
            username=display_id,
            tiktok_status_code=status,
            stage="profile_metadata",
        )
        if status == 209002:
            self.raise_login_required(
                "TikTok is requiring login for audience controls, status code 209002"
            )
        if status == 10221:
            # TikTok does not distinguish removal, renaming or access limits here.
            raise ExtractorError(
                "TikTok did not return a profile for this username, status code 10221",
                expected=True,
            )
        return data


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
        logger.warning(
            "tiktok_profile_classified",
            outcome="restricted",
            tiktok_status_code=209002 if "status code 209002" in message else None,
        )
        raise FeedUnavailable(url, "tiktok_profile_restricted", retry_at)

    if (
        "Unable to extract secondary user ID" in message
        or "status code 10221" in message
    ):
        retry_at = datetime.now(UTC) + timedelta(hours=1)
        logger.warning(
            "tiktok_profile_classified",
            outcome="unavailable",
            tiktok_status_code=10221 if "status code 10221" in message else None,
        )
        raise FeedUnavailable(url, "tiktok_profile_unavailable", retry_at)

    # yt-dlp can return [None] after a playlist request fails. Only real
    # video links make an errored extraction useful as a partial result.
    entries = info.get("entries") if info else None
    has_links = isinstance(entries, list) and any(
        _has_video_link(entry) for entry in entries
    )
    if info is not None and has_links and error:
        logger.warning("tiktok_profile_classified", outcome="partial")
        return {**info, "tiktok_outcome": "partial", "extraction_incomplete": True}

    if info is None or error or (entries != [] and not has_links):
        logger.warning("tiktok_profile_classified", outcome="extraction_failed")
        retry_at = datetime.now(UTC) + timedelta(minutes=15)
        raise FeedUnavailable(url, "tiktok_profile_extraction_failed", retry_at)

    if info.get("entries") == []:
        logger.warning("tiktok_profile_classified", outcome="empty_unverified")
        raise FeedUnavailable(url, "tiktok_profile_empty_unverified")

    logger.info("tiktok_profile_classified", outcome="videos_found")
    return {**info, "tiktok_outcome": "videos_found"}


def _has_video_link(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    url = entry.get("url") or entry.get("webpage_url")
    return isinstance(url, str) and bool(url.strip())
