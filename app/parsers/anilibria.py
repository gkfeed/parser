import json
from collections.abc import Mapping
from datetime import timedelta
from typing import Any, override
from urllib.parse import quote, urljoin, urlsplit

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.http import HttpParserExtension
from app.serializers.feed import Item
from app.utils.datetime import constant_datetime


class AnilibriaFeed(HttpParserExtension, CacheFeedExtension):
    _cache_storage_time_if_success = timedelta(days=1)
    _cache_storage_time = timedelta(seconds=5)
    _api_base_url = "https://aniliberty.top/api/v1/"
    _cdn_base_url = "https://cdn.anilibria.top/"

    @property
    @override
    async def items(self) -> list[Item]:
        release = self._parse_release(
            await self.get_html(
                urljoin(
                    self._api_base_url,
                    f"anime/releases/{quote(self._get_alias_from_url(), safe='')}",
                )
            )
        )
        show_title = self._required_string(release, "name", "main")
        episodes = release.get("episodes")
        if not isinstance(episodes, list):
            raise ValueError("Could not extract episodes from AniLibria API response")

        return [
            self._episode_to_item(show_title, episode)
            for episode in reversed(episodes)
            if isinstance(episode, Mapping)
        ]

    def _episode_to_item(
        self, show_title: str, episode: Mapping[str, Any]
    ) -> Item:
        episode_id = self._required_string(episode, "id")
        ordinal = episode.get("ordinal")
        if not isinstance(ordinal, int):
            raise ValueError("Could not extract episode ordinal")

        episode_text = f"{ordinal} эпизод"
        episode_name = episode.get("name")
        if isinstance(episode_name, str) and episode_name:
            episode_text += f" — {episode_name}"

        image_url = self._episode_image_url(episode)
        site_base_url = self._site_base_url()
        return Item(
            title=f"{show_title} {episode_text}",
            text=f'<img src="{image_url}" alt="episode"><br>{episode_text}',
            date=constant_datetime,
            link=urljoin(site_base_url, f"anime/video/episode/{episode_id}"),
        )

    def _get_alias_from_url(self) -> str:
        parts = [part for part in urlsplit(self.feed.url).path.split("/") if part]
        try:
            release_index = parts.index("release")
            alias = parts[release_index + 1]
        except (ValueError, IndexError):
            raise ValueError(f"Could not extract release alias from URL: {self.feed.url}")

        if not alias:
            raise ValueError(f"Could not extract release alias from URL: {self.feed.url}")
        return alias

    def _site_base_url(self) -> str:
        parsed_url = urlsplit(self.feed.url)
        return f"{parsed_url.scheme}://{parsed_url.netloc}/"

    def _episode_image_url(self, episode: Mapping[str, Any]) -> str:
        preview = episode.get("preview")
        if not isinstance(preview, Mapping):
            raise ValueError("Could not extract episode image URL")

        image_path = preview.get("src")
        if not isinstance(image_path, str) or not image_path:
            raise ValueError("Could not extract episode image URL")
        return urljoin(self._cdn_base_url, image_path)

    @staticmethod
    def _parse_release(response: bytes) -> Mapping[str, Any]:
        try:
            release = json.loads(response)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("AniLibria API returned invalid JSON") from error

        if not isinstance(release, Mapping):
            raise ValueError("AniLibria API returned an invalid release")
        return release

    @staticmethod
    def _required_string(data: Mapping[str, Any], *path: str) -> str:
        value: Any = data
        for key in path:
            if not isinstance(value, Mapping):
                raise ValueError(f"Could not extract {'.'.join(path)}")
            value = value.get(key)

        if not isinstance(value, str) or not value:
            raise ValueError(f"Could not extract {'.'.join(path)}")
        return value
