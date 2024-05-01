from app.serializers.feed import Item
from app.utils.datetime import constant_datetime

from app.extentions.parsers.selenium import SeleniumParserExtention


class SpotifyPlaylistFeed(SeleniumParserExtention):
    _selenium_wait_time = 10

    @property
    async def items(self) -> list[Item]:
        soup = await self.get_soup(self.feed.url)
        first_track = soup.find_all("img")[1].parent.parent.parent
        first_track_name = first_track.find_all("a")[0].div.text
        first_track_artist = first_track.find_all("a")[0].parent.span.div.a.text
        first_track_id = first_track.find_all("a")[0]["href"].split("/")[-1]

        return [
            Item(
                title=first_track_artist + " : " + first_track_name,
                text=first_track_id,
                date=constant_datetime,
                link=self.feed.url,
            )
        ]
