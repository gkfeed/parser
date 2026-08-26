import base64
import json
import re
from datetime import timedelta
from typing import ClassVar, override
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from bs4.element import Tag

from app.core.worker_kind import WorkerKind
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.serializers.feed import Item
from app.services.hash import HashService
from app.services.http import HttpRequestError, HttpService
from app.utils.datetime import constant_datetime
from app.workers.http import get_html


class InstagramFeed(ItemsHashExtension, HttpParserExtension, CacheFeedExtension):
    worker_kind = WorkerKind.HEAVY
    _cache_storage_time_if_success = timedelta(weeks=1)
    _max_media_items = 30
    _instagram_url = "https://www.instagram.com"
    _instagram_app_id = "936619743392459"
    _instagram_headers: ClassVar[dict[str, str]] = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    _instagram_crawler_headers: ClassVar[dict[str, str]] = {
        "User-Agent": "Googlebot/2.1 (+http://www.google.com/bot.html)",
        "Accept-Language": "en-US,en;q=0.9",
    }

    @override
    async def _generate_hash(self, item: Item) -> str:
        match = re.search(r'src="data:[^;]+;base64,([^"]+)"', item.text)
        if match:
            return HashService.hash_str(match.group(1))
        return HashService.hash_str(item.text)

    @property
    async def items(self) -> list[Item]:
        nodes = await self._get_crawler_profile_nodes()
        if not nodes:
            nodes = await self._get_profile_api_nodes()
        if not nodes:
            return []

        enriched_nodes: list[dict] = []
        for profile_node in nodes:
            shortcode = self._get_shortcode(profile_node)
            if not shortcode:
                enriched_nodes.append(profile_node)
                continue

            embed_node = await self._get_embed_node(shortcode)
            if embed_node:
                enriched_nodes.append(
                    {
                        **embed_node,
                        "shortcode": embed_node.get("shortcode", shortcode),
                    }
                )
            else:
                enriched_nodes.append(profile_node)

        media: list[tuple[str, str]] = []
        for node in enriched_nodes:
            shortcode = self._get_shortcode(node)
            if not shortcode:
                continue
            post_url = f"{self._instagram_url}/p/{shortcode}/"
            media.extend((url, post_url) for url in self._media_urls(node))
            if len(media) >= self._max_media_items:
                break

        items: list[Item] = []
        for media_url, post_url in media[: self._max_media_items]:
            item = await self._create_image_item(media_url, post_url)
            if item:
                items.append(item)
        return items

    async def _get_crawler_profile_nodes(self) -> list[dict]:
        try:
            html = await HttpService.get(
                f"{self._instagram_url}/{self._user_name}/",
                headers=self._instagram_crawler_headers,
            )
        except HttpRequestError:
            return []

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

        soup = BeautifulSoup(html, "html.parser")
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
        profile_url = (
            f"{self._instagram_url}/api/v1/users/web_profile_info/"
            f"?username={self._user_name}"
        )
        headers = {**self._instagram_headers, "X-IG-App-ID": self._instagram_app_id}

        try:
            response = await HttpService.get(profile_url, headers=headers)
            profile = json.loads(response)
            edges = profile["data"]["user"]["edge_owner_to_timeline_media"]["edges"]
        except (HttpRequestError, json.JSONDecodeError, KeyError, TypeError):
            return []
        return [
            edge["node"]
            for edge in edges
            if isinstance(edge, dict) and isinstance(edge.get("node"), dict)
        ]

    @staticmethod
    def _get_shortcode(node: dict) -> str | None:
        shortcode = node.get("shortcode")
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

    async def _get_embed_node(self, shortcode: str) -> dict | None:
        url = f"{self._instagram_url}/p/{shortcode}/embed/captioned/"
        try:
            html = await HttpService.get(url, headers=self._instagram_headers)
        except HttpRequestError:
            return None
        return self._find_media_node(BeautifulSoup(html, "html.parser"))

    @staticmethod
    def _find_media_node(soup: BeautifulSoup) -> dict | None:
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
    def _media_urls(node: dict) -> list[str]:
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

    async def _create_image_item(self, src: str, link: str) -> Item | None:
        try:
            img_bytes = await get_html(src)
        except HttpRequestError:
            return None

        encoded = base64.b64encode(img_bytes).decode("utf-8")
        mime_type = self._get_mime_type(img_bytes)
        img_tag = (
            f'<img src="data:{mime_type};base64,{encoded}" alt="{self._user_name}" />'
        )
        return Item(
            title="inst: " + self._user_name,
            text=f"{self._user_name}<br>{img_tag}",
            date=constant_datetime,
            link=link,
        )

    @staticmethod
    def _get_mime_type(data: bytes) -> str:
        if data.startswith(b"\xff\xd8"):
            return "image/jpeg"
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if data.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
            return "image/webp"
        return "image/jpeg"

    @property
    def _user_name(self) -> str:
        path = urlparse(self.feed.url).path.rstrip("/")
        return path.rsplit("/", 1)[-1].removeprefix("@")
