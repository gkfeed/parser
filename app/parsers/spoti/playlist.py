from bs4 import Tag
from app.serializers.feed import Item
from app.utils.datetime import constant_datetime

from app.extensions.parsers.selenium import SeleniumParserExtension


class SpotifyPlaylistFeed(SeleniumParserExtension):
    _selenium_wait_time = 10

    @property
    async def items(self) -> list[Item]:
        soup = await self.get_soup(self.feed.url)
        first_track = self._get_first_track_element(soup)

        if not first_track:
            raise ValueError("Could not find the first track element.")

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

    def _get_first_track_element(self, soup: Tag) -> Tag | None:
        img_tags = soup.find_all("img")
        if (
            len(img_tags) > 1
            and isinstance(img_tags[1], Tag)
            and img_tags[1].parent
            and isinstance(img_tags[1].parent, Tag)
            and img_tags[1].parent.parent
            and isinstance(img_tags[1].parent.parent, Tag)
            and img_tags[1].parent.parent.parent
            and isinstance(img_tags[1].parent.parent.parent, Tag)
        ):
            return img_tags[1].parent.parent.parent
        return None

    def _get_track_anchor_tag(self, first_track: Tag) -> Tag:
        a_tags = first_track.find_all("a")
        if not (a_tags and isinstance(a_tags[0], Tag)):
            raise ValueError("Could not find the anchor tag for the track.")
        return a_tags[0]

    def _get_track_name(self, anchor_tag: Tag) -> str:
        div_tag = anchor_tag.find("div")
        if not (div_tag and isinstance(div_tag, Tag)):
            raise ValueError("Could not find the div tag for the track name.")
        return div_tag.text

    def _get_track_artist(self, anchor_tag: Tag) -> str:
        if not (anchor_tag.parent and isinstance(anchor_tag.parent, Tag)):
            raise ValueError("Could not find the parent of the anchor tag.")

        span_tags = anchor_tag.parent.find_all("span")
        if not (span_tags and len(span_tags) > 0 and isinstance(span_tags[-1], Tag)):
            raise ValueError("Could not find the span tag for the artist.")

        artist_a_tag = span_tags[-1].find("a")
        if not (artist_a_tag and isinstance(artist_a_tag, Tag)):
            raise ValueError("Could not find the artist anchor tag.")
        return artist_a_tag.text

    def _get_track_id(self, anchor_tag: Tag) -> str:
        if not ("href" in anchor_tag.attrs and isinstance(anchor_tag["href"], str)):
            raise ValueError("Could not find the href attribute for the track ID.")
        return anchor_tag["href"].split("/")[-1]
