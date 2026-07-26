from bs4 import Tag

from app.extensions.parsers.selenium import SeleniumParserExtension
from app.serializers.feed import Item
from app.utils.datetime import constant_datetime


class SpotifyPlaylistFeed(SeleniumParserExtension):
    _selenium_wait_time = 10

    @property
    async def items(self) -> list[Item]:
        soup = await self.get_soup(self.feed.url)
        first_track = self._get_first_track_element(soup)
        anchor_tag = self._get_track_anchor_tag(first_track)
        first_track_name = self._get_track_name(anchor_tag)
        first_track_artist = self._get_track_artist(anchor_tag)
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
        track_anchor = soup.find(
            "a",
            href=lambda href: isinstance(href, str) and href.startswith("/track/"),
        )
        if not isinstance(track_anchor, Tag):
            raise ValueError(  # noqa: TRY004 - missing page data is a value error
                "Could not find the first track element."
            )

        track_element = track_anchor.parent
        while isinstance(track_element, Tag):
            artist_anchor = track_element.find(
                "a",
                href=lambda href: isinstance(href, str)
                and href.startswith("/artist/"),
            )
            if isinstance(artist_anchor, Tag):
                return track_element
            track_element = track_element.parent

        raise ValueError("Could not find the first track artist.")

    def _get_track_anchor_tag(self, first_track: Tag) -> Tag:
        anchor_tag = first_track.find(
            "a",
            href=lambda href: isinstance(href, str) and href.startswith("/track/"),
        )
        if not isinstance(anchor_tag, Tag):
            raise ValueError(  # noqa: TRY004 - missing page data is a value error
                "Could not find the anchor tag for the track."
            )
        return anchor_tag

    def _get_track_name(self, anchor_tag: Tag) -> str:
        track_name = anchor_tag.get_text(strip=True)
        if not track_name:
            raise ValueError("Could not find the track name.")
        return track_name

    def _get_track_artist(self, anchor_tag: Tag) -> str:
        track_element = anchor_tag.parent
        while isinstance(track_element, Tag):
            artist_tags = track_element.find_all(
                "a",
                href=lambda href: isinstance(href, str)
                and href.startswith("/artist/"),
            )
            artist_names = [tag.get_text(strip=True) for tag in artist_tags]
            artist_names = [name for name in artist_names if name]
            if artist_names:
                return ", ".join(artist_names)
            track_element = track_element.parent

        raise ValueError("Could not find the artist anchor tag.")

    def _get_track_id(self, anchor_tag: Tag) -> str:
        href = anchor_tag.get("href")
        if not isinstance(href, str) or not href.startswith("/track/"):
            raise ValueError("Could not find the href attribute for the track ID.")
        return href.removeprefix("/track/").split("?", maxsplit=1)[0].rstrip("/")
