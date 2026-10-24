import json
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from time import monotonic
from typing import ClassVar

import structlog

from app.extensions.parsers.exceptions import FeedUnavailable
from app.services.cache.temporary import TemporaryCacheService
from app.services.http import HttpRequestError, HttpResponse, HttpService
from app.services.instagram_responses import (
    InstagramPost,
    InstagramProfile,
    InstagramResponseAdapter,
    InstagramResponseError,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class InstagramMedia:
    url: str
    post_url: str


class InstagramService:
    _base_url = "https://www.instagram.com"
    _app_id = "936619743392459"
    _profile_feed_count = 12
    _max_media_items = 30
    _headers: ClassVar[dict[str, str]] = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    _crawler_headers: ClassVar[dict[str, str]] = {
        "User-Agent": "Googlebot/2.1 (+http://www.google.com/bot.html)",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(self, username: str, cache: TemporaryCacheService[bytes]) -> None:
        self._username = username
        self._cache = cache
        self._retry_times: list[datetime] = []
        self._logger = logger.bind(username=username)
        self._source_details: dict[str, dict[str, object]] = {}
        self._source_outcomes: dict[str, str] = {}

    async def get_media(self) -> list[InstagramMedia]:
        self._retry_times.clear()
        self._source_details.clear()
        self._source_outcomes.clear()
        started = monotonic()
        for source, fetch in (
            ("crawler", self._get_crawler_profile),
            ("profile-api", self._get_api_profile),
            ("profile-feed", self._get_feed_profile),
        ):
            profile = await fetch()
            if profile is None:
                continue
            self._logger.info(
                "instagram_profile_fetched",
                source=source,
                nodes=len(profile.posts),
                profile_state=profile.state,
                fallback_used=source != "crawler",
                **self._source_details.get(source, {}),
            )
            if profile.state == "private":
                raise FeedUnavailable(
                    f"{self._base_url}/{self._username}/",
                    "private_profile",
                    datetime.now(UTC) + timedelta(days=1),
                )
            if profile.state == "empty":
                return []
            try:
                return await self._extract_media(profile.posts)
            except InstagramResponseError as exc:
                self._log_failure(source, str(exc))

        retry_at = min(self._retry_times) if len(self._retry_times) == 2 else None
        self._logger.warning(
            "instagram_profile_unavailable",
            crawler_outcome=self._source_outcomes.get("crawler"),
            profile_api_outcome=self._source_outcomes.get("profile-api"),
            profile_feed_outcome=self._source_outcomes.get("profile-feed"),
            retry_at=retry_at.isoformat() if retry_at else None,
            duration_seconds=round(monotonic() - started, 3),
        )
        raise FeedUnavailable(
            f"{self._base_url}/{self._username}/", "profile_unavailable", retry_at
        )

    def _log_failure(self, source: str, reason: str, **details: object) -> None:
        self._source_outcomes[source] = reason
        self._logger.warning(
            "instagram_request_failed",
            source=source,
            reason=reason,
            **{**self._source_details.get(source, {}), **details},
        )

    async def _get_response(
        self, url: str, headers: dict[str, str], source: str
    ) -> HttpResponse | None:
        started = monotonic()
        try:
            response = await HttpService.get_response(url, headers=headers)
        except HttpRequestError as exc:
            self._log_failure(
                source,
                "network",
                status=exc.status,
                exception_type=type(exc.__cause__ or exc).__name__,
                request_seconds=round(monotonic() - started, 3),
            )
            return None
        content_type = response.headers.get("content-type", "").split(";", 1)[0]
        self._source_details[source] = {
            "status": response.status,
            "response_bytes": len(response.content),
            "content_type": content_type
            if content_type in ("application/json", "text/html", "text/plain")
            else "other",
            "request_seconds": round(monotonic() - started, 3),
            "retry_after_present": "retry-after" in response.headers,
        }
        return response

    async def _extract_media(
        self, posts: tuple[InstagramPost, ...]
    ) -> list[InstagramMedia]:
        media: list[InstagramMedia] = []
        for post in posts:
            urls = post.image_urls
            if not urls:
                enriched = await self._get_embed_post(post.shortcode)
                urls = enriched.image_urls
            post_url = f"{self._base_url}/p/{post.shortcode}/"
            media.extend(InstagramMedia(url=url, post_url=post_url) for url in urls)
            if len(media) >= self._max_media_items:
                break
        return media[: self._max_media_items]

    def _adapt_profile(
        self, source: str, parse: Callable[[InstagramResponseAdapter], InstagramProfile]
    ) -> InstagramProfile | None:
        adapter = InstagramResponseAdapter(
            self._username, self._source_details.setdefault(source, {})
        )
        try:
            return parse(adapter)
        except InstagramResponseError as exc:
            self._log_failure(source, str(exc))
            return None

    async def _get_crawler_profile(self) -> InstagramProfile | None:
        response = await self._get_response(
            f"{self._base_url}/{self._username}/", self._crawler_headers, "crawler"
        )
        if response is None:
            return None
        if not 200 <= response.status < 300:
            self._log_failure("crawler", "http_error")
            return None

        return self._adapt_profile(
            "crawler", lambda adapter: adapter.crawler(response.content)
        )

    async def _get_api_profile(self) -> InstagramProfile | None:
        url = (
            f"{self._base_url}/api/v1/users/web_profile_info/?username={self._username}"
        )
        headers = {**self._headers, "X-IG-App-ID": self._app_id}
        profile = await self._get_api_json(url, headers, "profile-api")
        if profile is None:
            return None
        return self._adapt_profile(
            "profile-api", lambda adapter: adapter.profile_api(profile)
        )

    async def _get_feed_profile(self) -> InstagramProfile | None:
        url = (
            f"{self._base_url}/api/v1/feed/user/{self._username}/username/"
            f"?count={self._profile_feed_count}"
        )
        headers = {
            **self._headers,
            "X-IG-App-ID": self._app_id,
            "X-ASBD-ID": "198387",
            "Referer": f"{self._base_url}/{self._username}/",
        }
        profile = await self._get_api_json(url, headers, "profile-feed")
        if profile is None:
            return None
        return self._adapt_profile(
            "profile-feed", lambda adapter: adapter.profile_feed(profile)
        )

    async def _get_api_json(
        self, url: str, headers: dict[str, str], source: str
    ) -> dict[str, object] | None:
        for reason in ("rate-limited", "authentication-required"):
            key = f"instagram:{source}:{reason}"
            if not self._cache.has_valid_cache(key):
                continue
            retry_at = self._cache.get_expiry(key)
            if retry_at is not None:
                self._retry_times.append(retry_at)
            self._source_outcomes[source] = f"skipped:{reason}"
            self._logger.info(
                "instagram_api_skipped",
                source=source,
                reason=reason,
                retry_at=retry_at.isoformat() if retry_at else None,
                cooldown_scope="source",
            )
            return None

        response = await self._get_response(url, headers, source)
        if response is None:
            return None
        try:
            profile = json.loads(response.content)
            json_state = "object" if isinstance(profile, dict) else "non_object"
        except (ValueError, RecursionError):
            # Malformed diagnostic bodies must not bypass HTTP error/cooldown handling.
            profile = None
            json_state = "invalid"
        self._source_details[source]["json_state"] = json_state
        if isinstance(profile, dict):
            self._source_details[source].update(
                api_status=profile.get("status")
                if profile.get("status") in ("ok", "fail")
                else "other",
                require_login=profile.get("require_login")
                if type(profile.get("require_login")) is bool
                else None,
                challenge_present=isinstance(profile.get("challenge"), dict),
            )
        if response.status in (401, 429):
            self._pause_api(
                source, response.status, response.headers.get("retry-after")
            )
            return None
        if not 200 <= response.status < 300:
            self._log_failure(source, "http_error")
            return None
        if not isinstance(profile, dict) or profile.get("status") == "fail":
            self._log_failure(source, "invalid_response")
            return None
        self._cache.set_with_expiry(
            f"instagram:{source}:rate-limited:backoff", b"0", timedelta()
        )
        return profile

    def _pause_api(self, source: str, status: int, retry_after: str | None) -> None:
        reason = "authentication-required" if status == 401 else "rate-limited"
        key = f"instagram:{source}:{reason}"
        cooldown = timedelta(hours=1)
        cooldown_basis = "default"
        if status == 429:
            cooldown_basis = "backoff"
            backoff_key = f"{key}:backoff"
            previous_hours = (
                int(self._cache.get(backoff_key))
                if self._cache.has_valid_cache(backoff_key)
                else 0
            )
            hours = min(max(previous_hours * 2, 1), 8)
            cooldown = timedelta(hours=hours) * random.uniform(0.9, 1.1)
            self._cache.set_with_expiry(
                backoff_key, str(hours).encode(), timedelta(days=1)
            )
            server_delay = self._retry_after_delay(retry_after)
            if server_delay is not None:
                cooldown = server_delay
                cooldown_basis = "retry_after"
        retry_at = datetime.now(UTC) + cooldown
        self._cache.set_with_expiry(key, b"1", cooldown)
        self._retry_times.append(retry_at)
        self._source_outcomes[source] = reason
        self._logger.warning(
            "instagram_api_paused",
            source=source,
            reason=reason,
            cooldown_seconds=cooldown.total_seconds(),
            cooldown_basis=cooldown_basis,
            cooldown_scope="source",
            retry_at=retry_at.isoformat(),
            **self._source_details[source],
        )

    @staticmethod
    def _retry_after_delay(value: str | None) -> timedelta | None:
        if value is None:
            return None
        value = value.strip()
        try:
            if value.isdecimal():
                return timedelta(seconds=max(int(value), 1))
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=UTC)
            return max(date - datetime.now(UTC), timedelta(seconds=1))
        except (ValueError, TypeError, OverflowError):
            return None

    async def _get_embed_post(self, shortcode: str) -> InstagramPost:
        url = f"{self._base_url}/p/{shortcode}/embed/captioned/"
        try:
            html = await HttpService.get(url, headers=self._headers)
        except HttpRequestError as exc:
            self._log_failure("embed", "network_or_http_error", status=exc.status)
            raise InstagramResponseError("missing_media") from exc
        try:
            return InstagramResponseAdapter(self._username, {}).embed(html, shortcode)
        except InstagramResponseError as exc:
            self._log_failure("embed", str(exc))
            raise
