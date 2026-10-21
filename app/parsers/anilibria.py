from datetime import timedelta
from typing import override
from urllib.parse import urljoin, urlsplit

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemIdentityHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.serializers.feed import Item
from app.services.anilibria import AnilibriaClient, AnilibriaEpisode
from app.utils.datetime import constant_datetime


class AnilibriaFeed(ItemIdentityHashExtension, HttpParserExtension, CacheFeedExtension):
    _cache_storage_time_if_success = timedelta(days=1)
    _cache_storage_time = timedelta(seconds=5)

    @override
    async def _parse_items(self) -> list[Item]:
        release = await AnilibriaClient(self.get_html).get_release(
            self._get_alias_from_url()
        )
        return [
            self._episode_to_item(release.title, episode)
            for episode in reversed(release.episodes)
        ]

    def _episode_to_item(self, show_title: str, episode: AnilibriaEpisode) -> Item:
        episode_text = f"{episode.ordinal} эпизод"
        if episode.name:
            episode_text += f" — {episode.name}"

        return Item(
            title=f"{show_title} {episode_text}",
            text=f'<img src="{episode.image_url}" alt="episode"><br>{episode_text}',
            date=constant_datetime,
            link=urljoin(self._site_base_url(), f"anime/video/episode/{episode.id}"),
        )

    def _get_alias_from_url(self) -> str:
        parts = [part for part in urlsplit(self.feed.url).path.split("/") if part]
        try:
            release_index = parts.index("release")
            alias = parts[release_index + 1]
        except (ValueError, IndexError):
            raise ValueError(
                f"Could not extract release alias from URL: {self.feed.url}"
            )
        return alias

    def _site_base_url(self) -> str:
        parsed_url = urlsplit(self.feed.url)
        return f"{parsed_url.scheme}://{parsed_url.netloc}/"
