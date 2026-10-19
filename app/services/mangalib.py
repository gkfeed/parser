import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar

from app.services.http import HttpService


@dataclass(frozen=True)
class MangaLibChapter:
    volume: str
    number: str
    name: str | None
    created_at: datetime


class MangaLibClient:
    headers: ClassVar[dict[str, str]] = {
        **HttpService.headers,
        "Accept": "application/json",
        "Site-Id": "1",
        "Referer": "https://mangalib.org/",
    }
    _api_base_url = "https://api.cdnlibs.org/api/manga/"

    def __init__(self, fetch: Callable[[str], Awaitable[bytes]]) -> None:
        self._fetch = fetch

    async def get_chapters(self, slug: str, limit: int) -> list[MangaLibChapter]:
        response = await self._fetch(f"{self._api_base_url}{slug}/chapters")
        try:
            payload = json.loads(response)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("MangaLib API returned invalid JSON") from error
        chapters = payload.get("data") if isinstance(payload, Mapping) else None
        if not isinstance(chapters, list):
            raise ValueError(  # noqa: TRY004 - malformed API data is a value error
                "MangaLib API returned invalid chapter data"
            )
        return [self._parse_chapter(chapter) for chapter in reversed(chapters[-limit:])]

    @classmethod
    def _parse_chapter(cls, chapter: object) -> MangaLibChapter:
        if not isinstance(chapter, Mapping):
            raise ValueError(  # noqa: TRY004 - malformed API data is a value error
                "MangaLib API returned an invalid chapter"
            )
        volume = cls._required_string(chapter, "volume")
        number = cls._required_string(chapter, "number")
        name = chapter.get("name")
        return MangaLibChapter(
            volume,
            number,
            name if isinstance(name, str) else None,
            cls._get_created_at(chapter),
        )

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
            raise ValueError(  # noqa: TRY004 - malformed API data is a value error
                "Could not extract chapter branch"
            )
        created_at = branch.get("created_at")
        if not isinstance(created_at, str):
            raise ValueError(  # noqa: TRY004 - malformed API data is a value error
                "Could not extract chapter creation date"
            )
        try:
            return datetime.fromisoformat(created_at)
        except ValueError as error:
            raise ValueError("Invalid MangaLib chapter creation date") from error
