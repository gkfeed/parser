import json
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any, ClassVar, cast, override
from urllib.parse import urlsplit

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.http import HttpParserExtension
from app.serializers.feed import Item


class MangaLibFeed(HttpParserExtension, CacheFeedExtension):
    _headers: ClassVar[dict[str, str]] = {
        **HttpParserExtension._headers,
        "Accept": "application/json",
        "Site-Id": "1",
        "Referer": "https://mangalib.org/",
    }
    _cache_storage_time = timedelta(hours=1)
    _api_base_url = "https://api.cdnlibs.org/api/manga/"
    _max_posts = 5

    @override
    async def _parse_items(self) -> list[Item]:
        chapters = self._parse_chapters(
            await self.get_html(f"{self._api_base_url}{self._get_slug()}/chapters")
        )
        return [
            self._chapter_to_item(cast("Mapping[str, Any]", chapter))
            for chapter in reversed(chapters[-self._max_posts :])
        ]

    def _chapter_to_item(self, chapter: Mapping[str, Any]) -> Item:
        volume = self._required_string(chapter, "volume")
        number = self._required_string(chapter, "number")
        name = chapter.get("name")
        title = f"Том {volume}, Глава {number}"
        if isinstance(name, str) and name:
            title += f" — {name}"

        return Item(
            title=title,
            text=title,
            date=self._get_created_at(chapter),
            link=f"{self._site_base_url()}/ru/{self._get_slug()}/read/v{volume}/c{number}",
        )

    def _get_slug(self) -> str:
        parts = [part for part in urlsplit(self.feed.url).path.split("/") if part]
        if "manga" in parts:
            manga_index = parts.index("manga")
            if manga_index + 1 < len(parts):
                return parts[manga_index + 1]
        raise ValueError(f"Could not extract manga slug from URL: {self.feed.url}")

    def _site_base_url(self) -> str:
        parsed_url = urlsplit(self.feed.url)
        return f"{parsed_url.scheme}://{parsed_url.netloc}"

    @staticmethod
    def _parse_chapters(response: bytes) -> list[Any]:
        try:
            payload = json.loads(response)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("MangaLib API returned invalid JSON") from error

        chapters = payload.get("data") if isinstance(payload, Mapping) else None
        if not isinstance(chapters, list):
            raise ValueError(  # noqa: TRY004 - malformed parser data is a value error
                "MangaLib API returned invalid chapter data"
            )
        return chapters

    @staticmethod
    def _required_string(chapter: Mapping[str, Any], key: str) -> str:
        value = chapter.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Could not extract chapter {key}")
        return value

    @staticmethod
    def _get_created_at(chapter: Mapping[str, Any]) -> datetime:
        branches = chapter.get("branches")
        if not isinstance(branches, list) or not branches:
            raise ValueError("Could not extract chapter branch")
        branch = branches[0]
        if not isinstance(branch, Mapping):
            raise ValueError(  # noqa: TRY004 - malformed parser data is a value error
                "Could not extract chapter branch"
            )
        created_at = branch.get("created_at")
        if not isinstance(created_at, str):
            raise ValueError(  # noqa: TRY004 - malformed parser data is a value error
                "Could not extract chapter creation date"
            )
        return datetime.fromisoformat(created_at)
