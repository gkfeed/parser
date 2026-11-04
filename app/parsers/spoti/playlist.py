from urllib.parse import urlsplit

from bs4 import Tag

from app.extensions.parsers.hash import ItemIdentityHashExtension
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.serializers.feed import Item
from app.utils.datetime import constant_datetime


class SpotifyPlaylistFeed(ItemIdentityHashExtension, SeleniumParserExtension):
    _selenium_wait_time = 10

    async def _parse_items(self) -> list[Item]:
        soup = await self.get_soup(self.feed.url)
        anchor_tag = self._get_track_anchor_tag(soup)
        first_track = self._get_track_container(anchor_tag)
        first_track_name = self._get_track_name(anchor_tag)
        first_track_artist = self._get_artist_names(first_track)
        first_track_id = self._get_track_id(anchor_tag)

        return [
            Item(
                title=first_track_artist + " : " + first_track_name,
                text=first_track_id,
                date=constant_datetime,
                link=self.feed.url,
            )
        ]

    def _get_first_track_element(self, soup: Tag) -> Tag:
        track_anchor = self._get_track_anchor_tag(soup)
        return self._get_track_container(track_anchor)

    def _get_track_container(self, track_anchor: Tag) -> Tag:
        track_element = track_anchor.find_parent(
            lambda tag: (
                tag.get("data-testid") == "tracklist-row"
                or tag.get("role") == "row"
                or "track-row" in tag.get_attribute_list("class")
            )
        )
        if not isinstance(track_element, Tag):
            raise ValueError(  # noqa: TRY004 - missing page data is a value error
                "Could not find the first track row container."
            )
        return track_element

    def _get_track_anchor_tag(self, first_track: Tag) -> Tag:
        anchor_tag = first_track.find(
            "a",
            href=lambda href: isinstance(href, str) and href.startswith("/track/"),
        )
        if not isinstance(anchor_tag, Tag):
            raise ValueError(  # noqa: TRY004 - missing page data is a value error
                "Could not find the first track element."
            )
        return anchor_tag

    def _get_track_name(self, anchor_tag: Tag) -> str:
        track_name = anchor_tag.get_text(strip=True)
        if not track_name:
            raise ValueError("Could not find the track name.")
        return track_name

    def _get_track_artist(self, anchor_tag: Tag) -> str:
        return self._get_artist_names(self._get_track_container(anchor_tag))

    def _get_artist_names(self, track_container: Tag) -> str:
        artist_tags = track_container.find_all(
            "a",
            href=lambda href: isinstance(href, str) and href.startswith("/artist/"),
        )
        artist_names = [tag.get_text(strip=True) for tag in artist_tags]
        artist_names = [name for name in artist_names if name]
        if artist_names:
            return ", ".join(artist_names)

        raise ValueError("Could not find the artist name in the first track row.")

    def _get_track_id(self, anchor_tag: Tag) -> str:
        href = anchor_tag.get("href")
        if not isinstance(href, str) or not href.startswith("/track/"):
            raise ValueError("Could not find the href attribute for the track ID.")
        track_id = urlsplit(href).path.removeprefix("/track/").rstrip("/")
        if not track_id.strip():
            raise ValueError("Could not find a non-empty ID in the first track link.")
        return track_id
