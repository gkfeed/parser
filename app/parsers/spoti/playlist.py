from app.serializers.feed import Item
from app.utils.datetime import constant_datetime
from app.utils.return_empty_when import async_return_empty_when
from app.extentions.parsers.exceptions import UnavailableFeed
from app.extentions.parsers.http import HttpParserExtention


class SpotifyPlaylistFeed(HttpParserExtention):
    _headers = {}

    @property
    @async_return_empty_when(UnavailableFeed, ValueError, TypeError)
    async def items(self) -> list[Item]:
        soup = await self.get_soup(self.feed.url)
        first_track = soup.find_all("img")[2].parent.parent.parent
        first_track_name = first_track.find_all("span")[-1].text
        first_track_artist = first_track.find_all("p")[-1].text
        first_track_id = first_track["aria-labelledby"].split(":")[-1][:-2]

        return [
            Item(
                title=first_track_artist + " : " + first_track_name,
                text=first_track_id,
                date=constant_datetime,
                link=self.feed.url,
            )
        ]
