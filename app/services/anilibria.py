import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urljoin

from app.extensions.parsers.exceptions import FeedUnavailable


@dataclass(frozen=True)
class AnilibriaEpisode:
    id: str
    ordinal: int
    name: str | None
    image_url: str


@dataclass(frozen=True)
class AnilibriaRelease:
    title: str
    episodes: list[AnilibriaEpisode]


class AnilibriaClient:
    _api_base_urls = (
        "https://aniliberty.top/api/v1/",
        "https://anilibria.top/api/v1/",
        "https://api.anilibria.app/api/v1/",
    )
    _cdn_base_url = "https://cdn.anilibria.top/"

    def __init__(self, fetch: Callable[[str], Awaitable[bytes]]) -> None:
        self._fetch = fetch

    async def get_release(self, alias: str) -> AnilibriaRelease:
        path = f"anime/releases/{quote(alias, safe='')}"
        last_error: ValueError | FeedUnavailable | None = None
        for base_url in self._api_base_urls:
            try:
                return self.parse_release(await self._fetch(urljoin(base_url, path)))
            except (ValueError, FeedUnavailable) as error:
                last_error = error

        if isinstance(last_error, FeedUnavailable):
            raise last_error
        raise ValueError("AniLibria API mirrors returned invalid data") from last_error

    @classmethod
    def parse_release(cls, response: bytes) -> AnilibriaRelease:
        try:
            release = json.loads(response)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("AniLibria API returned invalid JSON") from error
        if not isinstance(release, Mapping):
            raise ValueError(  # noqa: TRY004 - malformed API data is a value error
                "AniLibria API returned an invalid release"
            )

        title = cls._required_string(release, "name", "main")
        episodes = release.get("episodes")
        if not isinstance(episodes, list):
            raise ValueError(  # noqa: TRY004 - malformed API data is a value error
                "Could not extract episodes from AniLibria API response"
            )
        return AnilibriaRelease(
            title, [cls._parse_episode(value) for value in episodes]
        )

    @classmethod
    def _parse_episode(cls, episode: object) -> AnilibriaEpisode:
        if not isinstance(episode, Mapping):
            raise ValueError(  # noqa: TRY004 - malformed API data is a value error
                "Could not extract episode from AniLibria API response"
            )
        episode_id = cls._required_string(episode, "id")
        ordinal = episode.get("ordinal")
        if not isinstance(ordinal, int):
            raise ValueError(  # noqa: TRY004 - malformed API data is a value error
                "Could not extract episode ordinal"
            )
        name = episode.get("name")
        image_path = cls._required_string(episode, "preview", "src")
        return AnilibriaEpisode(
            episode_id,
            ordinal,
            name if isinstance(name, str) else None,
            urljoin(cls._cdn_base_url, image_path),
        )

    @staticmethod
    def _required_string(data: Mapping[str, Any], *path: str) -> str:
        value: Any = data
        for key in path:
            if not isinstance(value, Mapping):
                raise ValueError(  # noqa: TRY004 - malformed API data is a value error
                    f"Could not extract {'.'.join(path)}"
                )
            value = value.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Could not extract {'.'.join(path)}")
        return value
