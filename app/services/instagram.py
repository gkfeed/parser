import json
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import ClassVar

from bs4 import BeautifulSoup
from bs4.element import Tag

from app.services.cache.temporary import TemporaryCacheService
from app.services.http import HttpRequestError, HttpService


@dataclass(frozen=True)
class InstagramMedia:
    url: str
    post_url: str


class InstagramService:
    _base_url = "https://www.instagram.com"
    _app_id = "936619743392459"
    _profile_api_rate_limit_cooldown = timedelta(hours=1)
    _profile_api_rate_limit_cache_key = "instagram:profile-api:rate-limited"
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

    def __init__(
        self, username: str, cache: TemporaryCacheService[bytes]
    ) -> None:
        self._username = username
        self._cache = cache

    async def get_media(self) -> list[InstagramMedia]:
        nodes = await self._get_crawler_profile_nodes()
        if not nodes:
            nodes = await self._get_profile_api_nodes()
        if not nodes:
            nodes = await self._get_profile_feed_nodes()
        if not nodes:
            return []

        media: list[InstagramMedia] = []
        for profile_node in nodes:
            shortcode = self._get_shortcode(profile_node)
            if not shortcode:
                continue

            embed_node = await self._get_embed_node(shortcode)
            node = embed_node or profile_node
            shortcode = self._get_shortcode(node) or shortcode
            post_url = f"{self._base_url}/p/{shortcode}/"
            media.extend(
                InstagramMedia(url=url, post_url=post_url)
                for url in self._get_media_urls(node)
            )
            if len(media) >= self._max_media_items:
                break

        return media[: self._max_media_items]

    async def _get_crawler_profile_nodes(self) -> list[dict]:
        try:
            html = await HttpService.get(
                f"{self._base_url}/{self._username}/",
                headers=self._crawler_headers,
            )
        except HttpRequestError:
            return []

        soup = BeautifulSoup(html, "html.parser")
        nodes: list[dict] = []

        def collect(value: object) -> None:
            if isinstance(value, dict):
                if isinstance(value.get("pk"), str) and isinstance(
                    value.get("image_versions2"), dict
                ):
                    nodes.append(value)
                    return
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)

        for script in soup.find_all("script", {"type": "application/json"}):
            if not isinstance(script, Tag) or not script.string:
                continue
            try:
                collect(json.loads(script.string))
            except json.JSONDecodeError:
                continue

        unique_nodes: dict[str, dict] = {}
        for node in nodes:
            shortcode = self._get_shortcode(node)
            if shortcode:
                unique_nodes.setdefault(shortcode, node)
        return list(unique_nodes.values())

    async def _get_profile_api_nodes(self) -> list[dict]:
        if self._cache.has_valid_cache(self._profile_api_rate_limit_cache_key):
            return []

        url = (
            f"{self._base_url}/api/v1/users/web_profile_info/"
            f"?username={self._username}"
        )
        headers = {**self._headers, "X-IG-App-ID": self._app_id}

        try:
            status, response = await HttpService.get_with_status(url, headers=headers)
            if status == 429:
                self._cache.set_with_expiry(
                    self._profile_api_rate_limit_cache_key,
                    b"1",
                    self._profile_api_rate_limit_cooldown,
                )
                print(
                    "Instagram profile API rate limited; "
                    f"pausing requests for {self._profile_api_rate_limit_cooldown}"
                )
                return []
            if status >= 400:
                return []
            profile = json.loads(response)
            edges = profile["data"]["user"]["edge_owner_to_timeline_media"]["edges"]
        except (HttpRequestError, json.JSONDecodeError, KeyError, TypeError):
            return []
        return [
            edge["node"]
            for edge in edges
            if isinstance(edge, dict) and isinstance(edge.get("node"), dict)
        ]

    async def _get_profile_feed_nodes(self) -> list[dict]:
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

        try:
            status, response = await HttpService.get_with_status(url, headers=headers)
            if status >= 400:
                return []
            items = json.loads(response).get("items")
        except (HttpRequestError, json.JSONDecodeError, AttributeError, TypeError):
            return []
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict)]

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
                candidate = candidates[0]
                if isinstance(candidate, dict):
                    url = candidate.get("url")
            if not url:
                url = media_node.get("display_uri")
            if isinstance(url, str):
                urls.append(url)
        return urls
