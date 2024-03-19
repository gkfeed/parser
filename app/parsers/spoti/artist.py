from bs4.element import Tag

from app.serializers.feed import Item
from app.utils.datetime import constant_datetime
from app.utils.return_empty_when import async_return_empty_when
from app.extentions.parsers.exceptions import UnavailableFeed
from app.extentions.parsers.selenium import SeleniumParserExtention


class SpotifyFeed(SeleniumParserExtention):
    _selenium_wait_time = 10

    @property
    @async_return_empty_when(UnavailableFeed, ValueError, TypeError)
    async def items(self) -> list[Item]:
        artist_name = await self._artist_name
        return [
            Item(
                title=artist_name + " - " + link.text,
                text=link.text,
                date=constant_datetime,
                link="https://open.spotify.com" + link["href"],
            )
            for link in await self._releases_links
        ]

    @property
    async def _releases_links(self) -> list[Tag]:
        albums_soup = await self.get_soup(self.feed.url + "/discography/album")
        singles_soup = await self.get_soup(self.feed.url + "/discography/single")
        links = albums_soup.find_all("a") + singles_soup.find_all("a")

        releases_links = []
        for link in links:
            try:
                if link["href"].startswith("/album"):
                    releases_links.append(link)
            except KeyError:
                continue
        return releases_links

    @property
    async def _artist_name(self) -> str:
        soup = await self.get_soup(self.feed.url + "/discography/album")
        links = soup.find_all("a")
        for link in links:
            if link["href"].startswith("/artist"):
                return link.text
