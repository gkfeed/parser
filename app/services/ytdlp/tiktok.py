from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from yt_dlp.extractor.tiktok import TikTokUserIE as UpstreamTikTokUserIE
from yt_dlp.utils import ExtractorError

from app.extensions.parsers.exceptions import FeedUnavailable
from app.utils.logging import url_log_fields

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
    url: str,
    info: dict[str, Any] | None,
    error: str | None,
    warnings: tuple[str, ...] = (),
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
    url: str,
    info: dict[str, Any] | None,
    error: str | None,
    warnings: tuple[str, ...] = (),
) -> dict[str, Any]:
    message = error or ""
    log = logger.bind(**url_log_fields(url))
    if "This account does not have any videos posted" in message:
        log.info(
            "tiktok_profile_classified",
            outcome="empty_confirmed",
            diagnostic_subtype="no_videos_posted",
            stage="profile_metadata",
        )
        return {"entries": [], "tiktok_outcome": "empty_confirmed"}

    restriction = _profile_restriction(message)
    if restriction:
        retry_at = datetime.now(UTC) + timedelta(days=1)
        status = 209002 if "status code 209002" in message else None
        log.warning(
            "tiktok_profile_classified",
            outcome="restricted",
            diagnostic_subtype=restriction,
            stage="profile_metadata" if status else "profile_access",
            tiktok_status_code=status,
        )
        raise FeedUnavailable(url, "tiktok_profile_restricted", retry_at)

    if "status code 10221" in message:
        retry_at = datetime.now(UTC) + timedelta(hours=1)
        log.warning(
            "tiktok_profile_classified",
            outcome="unavailable",
            diagnostic_subtype="profile_not_returned",
            stage="profile_metadata",
            tiktok_status_code=10221,
        )
        raise FeedUnavailable(url, "tiktok_profile_unavailable", retry_at)

    if "Unable to extract secondary user ID" in message:
        retry_at = datetime.now(UTC) + timedelta(hours=1)
        # This warning means the embed fallback returned no page. yt-dlp's
        # access hint does not prove privacy or rule out a request failure.
        embed_unavailable = any(
            "account is either private or has embedding disabled" in warning
            for warning in warnings
        )
        log.warning(
            "tiktok_profile_classified",
            outcome="unavailable",
            diagnostic_subtype="secondary_user_id_missing",
            stage="profile_embed" if embed_unavailable else "profile_identity",
            access_hint="private_or_embedding_disabled" if embed_unavailable else None,
            tiktok_status_code=None,
        )
        raise FeedUnavailable(url, "tiktok_profile_unavailable", retry_at)

    # yt-dlp can return [None] after a playlist request fails. Only real
    # video links make an errored extraction useful as a partial result.
    entries = info.get("entries") if info else None
    has_links = isinstance(entries, list) and any(
        _has_video_link(entry) for entry in entries
    )
    if info is not None and has_links and error:
        log.warning(
            "tiktok_profile_classified",
            outcome="partial",
            diagnostic_subtype="extraction_error_with_links",
            stage="profile_listing",
        )
        return {**info, "tiktok_outcome": "partial", "extraction_incomplete": True}

    if info is None or error or (entries != [] and not has_links):
        subtype = "invalid_video_entries"
        if error:
            subtype = "unrecognized_extractor_error"
        elif info is None:
            subtype = "missing_extraction_result"
        log.warning(
            "tiktok_profile_classified",
            outcome="extraction_failed",
            diagnostic_subtype=subtype,
            stage="profile_listing",
        )
        retry_at = datetime.now(UTC) + timedelta(minutes=15)
        raise FeedUnavailable(url, "tiktok_profile_extraction_failed", retry_at)

    if info.get("entries") == []:
        log.warning(
            "tiktok_profile_classified",
            outcome="empty_unverified",
            diagnostic_subtype="empty_entries_without_confirmation",
            stage="profile_listing",
        )
        raise FeedUnavailable(url, "tiktok_profile_empty_unverified")

    log.info(
        "tiktok_profile_classified",
        outcome="videos_found",
        diagnostic_subtype="video_links_found",
        stage="profile_listing",
    )
    return {**info, "tiktok_outcome": "videos_found"}


def _profile_restriction(message: str) -> str | None:
    if "account is private" in message:
        return "account_private"
    if any(
        reason in message
        for reason in (
            "account is likely either private",
            "all of their videos are private",
        )
    ):
        return "account_or_videos_private"
    if "TikTok is requiring login" in message:
        return "login_required"
    return None


def _has_video_link(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    url = entry.get("url") or entry.get("webpage_url")
    return isinstance(url, str) and bool(url.strip())
