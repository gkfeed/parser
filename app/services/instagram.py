import json
import random
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import ClassVar, Literal

import structlog
from bs4 import BeautifulSoup
from bs4.element import Tag

from app.extensions.parsers.exceptions import FeedUnavailable
from app.services.cache.temporary import TemporaryCacheService
from app.services.http import HttpRequestError, HttpService

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class InstagramMedia:
    url: str
    post_url: str


@dataclass(frozen=True)
class InstagramProfile:
    nodes: list[dict]
    state: Literal["media", "empty", "private"]


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

    async def get_media(self) -> list[InstagramMedia]:
        self._retry_times.clear()
        for source, fetch in (
            ("crawler", self._get_crawler_profile_nodes),
            ("profile-api", self._get_profile_api_nodes),
            ("profile-feed", self._get_profile_feed_nodes),
        ):
            profile = await fetch()
            if profile is None:
                continue
            logger.info(
                "instagram_profile_fetched",
                source=source,
                nodes=len(profile.nodes),
                profile_state=profile.state,
            )
            if profile.state == "private":
                raise FeedUnavailable(
                    f"{self._base_url}/{self._username}/",
                    "private_profile",
                    datetime.now(UTC) + timedelta(days=1),
                )
            if profile.state == "empty":
                return []
            media = await self._extract_media(profile.nodes)
            if media:
                return media
            logger.warning(
                "instagram_request_failed", source=source, reason="missing_media"
            )

        retry_at = min(self._retry_times) if len(self._retry_times) == 2 else None
        raise FeedUnavailable(
            f"{self._base_url}/{self._username}/", "profile_unavailable", retry_at
        )

    async def _extract_media(self, nodes: list[dict]) -> list[InstagramMedia]:
        media: list[InstagramMedia] = []
        for profile_node in nodes:
            shortcode = self._get_shortcode(profile_node)
            if not shortcode:
                return []
            urls = self._get_media_urls(profile_node)
            if not urls:
                embed_node = await self._get_embed_node(shortcode)
                urls = self._get_media_urls(embed_node or profile_node)
            if not urls:
                return []
            post_url = f"{self._base_url}/p/{shortcode}/"
            media.extend(InstagramMedia(url=url, post_url=post_url) for url in urls)
            if len(media) >= self._max_media_items:
                break
        return media[: self._max_media_items]

    @staticmethod
    def _iter_dicts(value: object) -> Iterator[dict]:
        pending = [value]
        while pending:
            current = pending.pop()
            if isinstance(current, dict):
                yield current
                pending.extend(current.values())
            elif isinstance(current, list):
                pending.extend(current)

    async def _get_crawler_profile_nodes(self) -> InstagramProfile | None:
        try:
            status, html = await HttpService.get_with_status(
                f"{self._base_url}/{self._username}/", headers=self._crawler_headers
            )
        except HttpRequestError:
            logger.warning(
                "instagram_request_failed", source="crawler", reason="network"
            )
            return None
        if status >= 400:
            logger.warning("instagram_request_failed", source="crawler", status=status)
            return None

        soup = BeautifulSoup(html, "html.parser")
        objects: list[dict] = []
        for script in soup.find_all("script", {"type": "application/json"}):
            if not isinstance(script, Tag) or not script.string:
                continue
            try:
                objects.extend(self._iter_dicts(json.loads(script.string)))
            except json.JSONDecodeError:
                continue

        timeline_ids = {
            str(value["id"])
            for value in objects
            if value.get("id") is not None
            and isinstance(value.get("polaris_timeline_connection"), dict)
        }
        users = [
            value
            for value in objects
            if self._matches_username(value)
            and isinstance(value.get("is_private"), bool)
            and any(value.get(key) is not None for key in ("id", "pk"))
        ]
        user = max(
            users,
            key=lambda value: (
                any(str(value.get(key)) in timeline_ids for key in ("id", "pk")),
                sum(value.get(key) is not None for key in ("id", "pk")),
            ),
            default=None,
        )
        if user is None:
            logger.warning(
                "instagram_request_failed", source="crawler", reason="missing_profile"
            )
            return None
        if user["is_private"]:
            return InstagramProfile([], "private")

        user_ids = {str(user[key]) for key in ("id", "pk") if user.get(key) is not None}
        timelines = [
            value["polaris_timeline_connection"]
            for value in objects
            if str(value.get("id")) in user_ids
            and isinstance(value.get("polaris_timeline_connection"), dict)
        ]
        timeline = max(
            timelines,
            key=lambda value: (
                len(value["edges"]) if isinstance(value.get("edges"), list) else -1
            ),
            default=None,
        )
        # The crawler publishes the post count in metadata, separately from the
        # profile JSON. Only use metadata that names the requested account.
        media_count = None
        description = soup.find("meta", {"property": "og:description"})
        if isinstance(description, Tag):
            content = description.get("content")
            if isinstance(content, str) and re.search(
                rf"\(@{re.escape(self._username)}\)", content, re.IGNORECASE
            ):
                match = re.search(r"(?:^|, )([0-9,]+) Posts\b", content)
                if match:
                    media_count = int(match.group(1).replace(",", ""))
        return self._classify_profile(user, timeline, "crawler", media_count)

    def _matches_username(self, user: dict) -> bool:
        username = user.get("username")
        return (
            isinstance(username, str)
            and username.casefold() == self._username.casefold()
        )

    def _classify_profile(
        self,
        user: object,
        timeline: object,
        source: str,
        media_count: int | None = None,
    ) -> InstagramProfile | None:
        if not isinstance(user, dict) or not self._matches_username(user):
            logger.warning(
                "instagram_request_failed", source=source, reason="missing_profile"
            )
            return None
        if user.get("is_private") is True:
            return InstagramProfile([], "private")
        if not isinstance(timeline, dict) or not isinstance(
            timeline.get("edges"), list
        ):
            logger.warning(
                "instagram_request_failed", source=source, reason="missing_timeline"
            )
            return None
        edges = timeline["edges"]
        if any(
            not isinstance(edge, dict) or not isinstance(edge.get("node"), dict)
            for edge in edges
        ):
            logger.warning(
                "instagram_request_failed", source=source, reason="invalid_timeline"
            )
            return None
        if edges:
            return InstagramProfile([edge["node"] for edge in edges], "media")
        raw_counts = (user.get("media_count"), timeline.get("count"), media_count)
        counts = tuple(
            count for count in raw_counts if type(count) is int and count >= 0
        )
        page_info = timeline.get("page_info")
        has_more = (
            isinstance(page_info, dict) and page_info.get("has_next_page") is True
        )
        if (
            user.get("is_private") is False
            and counts
            and all(count == 0 for count in counts)
            and not has_more
        ):
            return InstagramProfile([], "empty")
        logger.warning(
            "instagram_request_failed",
            source=source,
            reason="unverified_empty_timeline",
        )
        return None

    async def _get_profile_api_nodes(self) -> InstagramProfile | None:
        url = (
            f"{self._base_url}/api/v1/users/web_profile_info/?username={self._username}"
        )
        headers = {**self._headers, "X-IG-App-ID": self._app_id}
        profile = await self._get_api_json(url, headers, "profile-api")
        if profile is None:
            return None
        data = profile.get("data")
        user = data.get("user") if isinstance(data, dict) else None
        timeline = (
            user.get("edge_owner_to_timeline_media") if isinstance(user, dict) else None
        )
        return self._classify_profile(user, timeline, "profile-api")

    async def _get_profile_feed_nodes(self) -> InstagramProfile | None:
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
        items = profile.get("items")
        if not isinstance(items, list) or any(
            not isinstance(item, dict) for item in items
        ):
            logger.warning(
                "instagram_request_failed",
                source="profile-feed",
                reason="invalid_timeline",
            )
            return None
        if any(
            isinstance(item.get("user"), dict)
            and not self._matches_username(item["user"])
            for item in items
        ):
            logger.warning(
                "instagram_request_failed",
                source="profile-feed",
                reason="profile_mismatch",
            )
            return None
        user = profile.get("user")
        if not isinstance(user, dict) and items:
            user = items[0].get("user")
        timeline = {"edges": [{"node": item} for item in items]}
        return self._classify_profile(user, timeline, "profile-feed")

    async def _get_api_json(
        self, url: str, headers: dict[str, str], source: str
    ) -> dict | None:
        for reason in ("rate-limited", "authentication-required"):
            key = f"instagram:{source}:{reason}"
            if not self._cache.has_valid_cache(key):
                continue
            retry_at = self._cache.get_expiry(key)
            if retry_at is not None:
                self._retry_times.append(retry_at)
            logger.info(
                "instagram_api_skipped",
                source=source,
                reason=reason,
                retry_at=retry_at.isoformat() if retry_at else None,
            )
            return None

        try:
            response = await HttpService.get_response(url, headers=headers)
        except HttpRequestError:
            logger.warning("instagram_request_failed", source=source, reason="network")
            return None
        if response.status in (401, 429):
            self._pause_api(
                source, response.status, response.headers.get("retry-after")
            )
            return None
        if response.status >= 400:
            logger.warning(
                "instagram_request_failed", source=source, status=response.status
            )
            return None
        try:
            profile = json.loads(response.content)
        except (json.JSONDecodeError, UnicodeDecodeError):
            profile = None
        if not isinstance(profile, dict) or profile.get("status") == "fail":
            logger.warning(
                "instagram_request_failed", source=source, reason="invalid_response"
            )
            return None
        self._cache.set_with_expiry(
            f"instagram:{source}:rate-limited:backoff", b"0", timedelta()
        )
        return profile

    def _pause_api(self, source: str, status: int, retry_after: str | None) -> None:
        reason = "authentication-required" if status == 401 else "rate-limited"
        key = f"instagram:{source}:{reason}"
        cooldown = timedelta(hours=1)
        if status == 429:
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
        retry_at = datetime.now(UTC) + cooldown
        self._cache.set_with_expiry(key, b"1", cooldown)
        self._retry_times.append(retry_at)
        logger.warning(
            "instagram_api_paused",
            source=source,
            reason=reason,
            status=status,
            cooldown_seconds=cooldown.total_seconds(),
            retry_at=retry_at.isoformat(),
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

    async def _get_embed_node(self, shortcode: str) -> dict | None:
        url = f"{self._base_url}/p/{shortcode}/embed/captioned/"
        try:
            html = await HttpService.get(url, headers=self._headers)
        except HttpRequestError:
            return None
        return self._find_media_node(BeautifulSoup(html, "html.parser"))

    @classmethod
    def _find_media_node(cls, soup: BeautifulSoup) -> dict | None:
        def find(value: object) -> dict | None:
            if isinstance(value, dict):
                for key in ("shortcode_media", "xdt_shortcode_media"):
                    node = value.get(key)
                    if isinstance(node, dict):
                        return node
                if isinstance(value.get("shortcode"), str) and any(
                    key in value for key in ("display_url", "edge_sidecar_to_children")
                ):
                    return value
                for child in value.values():
                    node = find(child)
                    if node:
                        return node
            elif isinstance(value, list):
                for child in value:
                    node = find(child)
                    if node:
                        return node
            elif isinstance(value, str) and "shortcode_media" in value:
                try:
                    return find(json.loads(value))
                except json.JSONDecodeError:
                    return None
            return None

        for script in soup.find_all("script"):
            if not isinstance(script, Tag):
                continue
            content = script.string
            if not content or "shortcode_media" not in content:
                continue
            try:
                node = find(json.loads(content))
            except json.JSONDecodeError:
                continue
            if node:
                return node
        return None

    @staticmethod
    def _get_shortcode(node: dict) -> str | None:
        shortcode = node.get("shortcode") or node.get("code")
        if isinstance(shortcode, str):
            return shortcode
        canonical_url = node.get("seo_canonical_url")
        if isinstance(canonical_url, str):
            match = re.search(r"/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)", canonical_url)
            if match:
                return match.group(1)

        media_id = node.get("pk")
        if type(media_id) is int:
            media_id = str(media_id)
        if not isinstance(media_id, str) or not media_id.isdecimal():
            return None
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        number = int(media_id)
        encoded = ""
        while number:
            encoded = alphabet[number % 64] + encoded
            number //= 64
        return encoded or "A"

    @staticmethod
    def _get_media_urls(node: dict) -> list[str]:
        sidecar = node.get("edge_sidecar_to_children")
        edges = sidecar.get("edges") if isinstance(sidecar, dict) else None
        carousel = node.get("carousel_media")
        if isinstance(edges, list) and edges:
            media_nodes = [edge.get("node") for edge in edges if isinstance(edge, dict)]
        elif isinstance(carousel, list) and carousel:
            media_nodes = carousel
        else:
            media_nodes = [node]

        urls: list[str] = []
        for media_node in media_nodes:
            if not isinstance(media_node, dict):
                continue
            # Signed video URLs expire. Persist the display image instead.
            url = media_node.get("display_url") or media_node.get("thumbnail_src")
            versions = media_node.get("image_versions2")
            candidates = (
                versions.get("candidates") if isinstance(versions, dict) else None
            )
            if not url and isinstance(candidates, list) and candidates:
                url = next(
                    (
                        candidate["url"]
                        for candidate in candidates
                        if isinstance(candidate, dict)
                        and isinstance(candidate.get("url"), str)
                    ),
                    None,
                )
            if not url:
                url = media_node.get("display_uri")
            if isinstance(url, str):
                urls.append(url)
        return urls
