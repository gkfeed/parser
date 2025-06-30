from bs4.element import Tag

from app.serializers.feed import Item
from app.utils.datetime import constant_datetime
from app.extensions.parsers.selenium import SeleniumParserExtension


class SpotifyFeed(SeleniumParserExtension):
    _selenium_wait_time = 10

    @property
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
        soup = await self.get_soup(self.feed.url + "/discography")
        links = soup.find_all("a")

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
        soup = await self.get_soup(self.feed.url + "/discography")
        links = soup.find_all("a")
        for link in links:
            if link["href"].startswith("/artist"):
                return link.text
