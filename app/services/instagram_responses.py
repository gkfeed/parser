"""Adapters for Instagram's remote payloads, isolated from HTTP and feed logic."""

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from bs4.element import Tag


class InstagramResponseError(ValueError):
    """A source cannot establish a valid profile or post."""


@dataclass(frozen=True)
class InstagramPost:
    shortcode: str
    image_urls: tuple[str, ...]


@dataclass(frozen=True)
class InstagramProfile:
    posts: tuple[InstagramPost, ...]
    state: Literal["media", "empty", "private"]


class InstagramResponseAdapter:
    def __init__(self, username: str, details: dict[str, object]) -> None:
        self._username = username
        self.details = details

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

    def crawler(self, content: bytes) -> InstagramProfile:
        soup = BeautifulSoup(content, "html.parser")
        objects: list[dict] = []
        invalid_json_scripts = 0
        for script in soup.find_all("script", {"type": "application/json"}):
            if not isinstance(script, Tag) or not script.string:
                continue
            try:
                objects.extend(self._iter_dicts(json.loads(script.string)))
            except (ValueError, RecursionError):
                invalid_json_scripts += 1
                continue

        self.details.update(
            json_objects=len(objects),
            invalid_json_scripts=invalid_json_scripts,
            description_present=soup.find("meta", {"property": "og:description"})
            is not None,
            **self._crawler_root_details(objects),
        )
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
        self.details["matching_profiles"] = len(users)
        user = max(
            users,
            key=lambda value: (
                any(str(value.get(key)) in timeline_ids for key in ("id", "pk")),
                sum(value.get(key) is not None for key in ("id", "pk")),
            ),
            default=None,
        )
        if user is None:
            raise InstagramResponseError("missing_profile")
        if user["is_private"]:
            self.details["is_private"] = True
            return InstagramProfile((), "private")

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
        return self._classify_profile(user, timeline, self._metadata_count(soup))

    def _metadata_count(self, soup: BeautifulSoup) -> int | None:
        description = soup.find("meta", {"property": "og:description"})
        if not isinstance(description, Tag):
            return None
        content = description.get("content")
        if not isinstance(content, str) or not re.search(
            rf"\(@{re.escape(self._username)}\)", content, re.IGNORECASE
        ):
            return None
        match = re.search(r"(?:^|, )([0-9,]+) Posts\b", content)
        if match is None:
            return None
        try:
            return int(match.group(1).replace(",", ""))
        except ValueError as exc:
            raise InstagramResponseError("invalid_media_count") from exc

    @staticmethod
    def _crawler_root_details(objects: list[dict]) -> dict[str, object]:
        for value in objects:
            root = value.get("rootView")
            if not isinstance(root, dict):
                continue
            resource = root.get("resource")
            component = resource.get("__dr") if isinstance(resource, dict) else None
            props = root.get("props")
            props = props if isinstance(props, dict) else {}
            # Never log arbitrary strings from HTML, including failure reasons.
            return {
                "root_component": component
                if component
                in (
                    "PolarisErrorRoot.react",
                    "PolarisProfilePostsLoggedOutTabGridRoot.react",
                    "PolarisLoggedOutMobileProfileRoot.react",
                )
                else "other",
                "root_failure_reason_present": props.get("failure_reason") is not None,
                "restricted_age_present": props.get("restricted_age") is not None,
            }
        return {"root_component": "missing"}

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
        media_count: int | None = None,
    ) -> InstagramProfile:
        if not isinstance(user, dict) or not self._matches_username(user):
            raise InstagramResponseError("missing_profile")
        if user.get("is_private") is True:
            self.details["is_private"] = True
            return InstagramProfile((), "private")
        if not isinstance(timeline, dict) or not isinstance(
            timeline.get("edges"), list
        ):
            raise InstagramResponseError("missing_timeline")
        if type(user.get("is_private")) is not bool:
            raise InstagramResponseError("invalid_profile")
        edges = timeline["edges"]
        page_info = timeline.get("page_info")
        has_next_page = (
            page_info.get("has_next_page") if isinstance(page_info, dict) else None
        )
        raw_counts = {
            "media_count": user.get("media_count"),
            "timeline_count": timeline.get("count"),
            "metadata_count": media_count,
        }
        if any(
            count is not None
            and (not isinstance(count, int) or isinstance(count, bool) or count < 0)
            for count in raw_counts.values()
        ):
            raise InstagramResponseError("invalid_media_count")
        if page_info is not None and not isinstance(page_info, dict):
            raise InstagramResponseError("invalid_page_info")
        if has_next_page is not None and type(has_next_page) is not bool:
            raise InstagramResponseError("invalid_page_info")
        counts = {
            key: count
            for key, count in raw_counts.items()
            if type(count) is int and count >= 0
        }
        self.details.update(
            counts,
            is_private=user.get("is_private")
            if type(user.get("is_private")) is bool
            else None,
            timeline_edges=len(edges),
            has_next_page=has_next_page if type(has_next_page) is bool else None,
        )
        if any(
            not isinstance(edge, dict) or not isinstance(edge.get("node"), dict)
            for edge in edges
        ):
            raise InstagramResponseError("invalid_timeline")
        if edges:
            return InstagramProfile(
                tuple(self._parse_post(edge["node"]) for edge in edges), "media"
            )
        if (
            user.get("is_private") is False
            and counts
            and all(count == 0 for count in counts.values())
            and has_next_page is not True
        ):
            return InstagramProfile((), "empty")
        raise InstagramResponseError("unverified_empty_timeline")

    def profile_api(self, payload: dict[str, object]) -> InstagramProfile:
        data = payload.get("data")
        user = data.get("user") if isinstance(data, dict) else None
        timeline = (
            user.get("edge_owner_to_timeline_media") if isinstance(user, dict) else None
        )
        return self._classify_profile(user, timeline)

    def profile_feed(self, payload: dict[str, object]) -> InstagramProfile:
        items = payload.get("items")
        if not isinstance(items, list) or any(
            not isinstance(item, dict) for item in items
        ):
            raise InstagramResponseError("invalid_timeline")
        if any(
            "user" in item
            and (
                not isinstance(item["user"], dict)
                or not self._matches_username(item["user"])
            )
            for item in items
        ):
            raise InstagramResponseError("profile_mismatch")
        user = payload.get("user")
        if user is None and items:
            user = items[0].get("user")
        timeline = {
            "edges": [{"node": item} for item in items],
            "page_info": {"has_next_page": payload.get("more_available")},
        }
        return self._classify_profile(user, timeline)

    @staticmethod
    def _get_shortcode(node: dict) -> str | None:
        shortcode = node.get("shortcode") or node.get("code")
        if isinstance(shortcode, str) and re.fullmatch(r"[A-Za-z0-9_-]+", shortcode):
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
        try:
            number = int(media_id)
        except ValueError as exc:
            raise InstagramResponseError("invalid_shortcode") from exc
        encoded = ""
        while number:
            encoded = alphabet[number % 64] + encoded
            number //= 64
        return encoded or "A"

    @classmethod
    def _parse_post(cls, node: dict) -> InstagramPost:
        shortcode = cls._get_shortcode(node)
        if shortcode is None:
            raise InstagramResponseError("invalid_shortcode")
        nodes = cls._media_nodes(node)
        # Entirely absent media can be enriched from the embed endpoint. A broken
        # carousel must never silently become a successful partial post.
        urls = tuple(cls._image_url(child) for child in nodes)
        if any(url is None for url in urls):
            return InstagramPost(shortcode, ())
        return InstagramPost(shortcode, tuple(url for url in urls if url is not None))

    @staticmethod
    def _media_nodes(node: dict) -> list[dict]:
        sidecar = node.get("edge_sidecar_to_children")
        if sidecar is not None:
            if not isinstance(sidecar, dict) or not isinstance(
                sidecar.get("edges"), list
            ):
                raise InstagramResponseError("invalid_carousel")
            edges = sidecar["edges"]
            if not edges or any(
                not isinstance(edge, dict) or not isinstance(edge.get("node"), dict)
                for edge in edges
            ):
                raise InstagramResponseError("invalid_carousel")
            return [edge["node"] for edge in edges]
        carousel = node.get("carousel_media")
        if carousel is None:
            return [node]
        if (
            not isinstance(carousel, list)
            or not carousel
            or any(not isinstance(child, dict) for child in carousel)
        ):
            raise InstagramResponseError("invalid_carousel")
        return carousel

    @classmethod
    def _image_url(cls, node: dict) -> str | None:
        for key in ("display_url", "thumbnail_src"):
            value = node.get(key)
            if value is not None:
                return cls._validate_url(value)
        versions = node.get("image_versions2")
        if versions is None:
            value = node.get("display_uri")
            return cls._validate_url(value) if value is not None else None
        if not isinstance(versions, dict) or not isinstance(
            versions.get("candidates"), list
        ):
            raise InstagramResponseError("invalid_image_versions")
        candidates = versions["candidates"]
        if not candidates:
            value = node.get("display_uri")
            return cls._validate_url(value) if value is not None else None
        urls = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                raise InstagramResponseError("invalid_image_versions")
            urls.append(cls._validate_url(candidate.get("url")))
        return urls[0]

    @staticmethod
    def _validate_url(value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise InstagramResponseError("invalid_media_url")
        try:
            parsed = urlsplit(value)
        except ValueError as exc:
            raise InstagramResponseError("invalid_media_url") from exc
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise InstagramResponseError("invalid_media_url")
        return value

    def embed(self, content: bytes, shortcode: str) -> InstagramPost:
        soup = BeautifulSoup(content, "html.parser")
        for script in soup.find_all("script"):
            if not isinstance(script, Tag) or not script.string:
                continue
            node = self._embed_script(script.string)
            if node is None:
                continue
            post = self._parse_post(node)
            if post.shortcode != shortcode:
                raise InstagramResponseError("embed_mismatch")
            if not post.image_urls:
                raise InstagramResponseError("missing_media")
            return post
        raise InstagramResponseError("missing_embed")

    @classmethod
    def _embed_script(cls, content: str) -> dict | None:
        for value in cls._embed_objects(content):
            node = cls._embed_node(value)
            if node is not None:
                return node
        return None

    @staticmethod
    def _embed_objects(content: str) -> Iterator[dict]:
        pending: list[object] = [content]
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                yield value
                pending.extend(reversed(list(value.values())))
                continue
            if isinstance(value, list):
                pending.extend(reversed(value))
                continue
            if not isinstance(value, str) or "shortcode_media" not in value:
                continue
            try:
                pending.append(json.loads(value))
            except (ValueError, RecursionError):
                continue

    @staticmethod
    def _embed_node(value: dict) -> dict | None:
        for key in ("shortcode_media", "xdt_shortcode_media"):
            node = value.get(key)
            if isinstance(node, dict):
                return node
        if isinstance(value.get("shortcode"), str) and any(
            key in value for key in ("display_url", "edge_sidecar_to_children")
        ):
            return value
        return None
