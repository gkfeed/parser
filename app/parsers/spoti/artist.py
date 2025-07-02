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
                title=self._extract_title(link, artist_name),
                text=self._extract_text(link),
                date=constant_datetime,
                link=self._extract_link(link),
            )
            for link in await self._releases_links
            if isinstance(link, Tag)
        ]

    async def _get_discography_soup(self):
        return await self.get_soup(self.feed.url + "/discography")

    async def _parse_releases_links(self, soup) -> list[Tag]:
        links = soup.find_all("a")

        releases_links = []
        for link in links:
            if isinstance(link, Tag) and "href" in link.attrs:
                href = link["href"]
                if isinstance(href, str) and href.startswith("/album"):
                    releases_links.append(link)
        return releases_links

    @property
    async def _releases_links(self) -> list[Tag]:
        soup = await self._get_discography_soup()
        return await self._parse_releases_links(soup)

    async def _parse_artist_name(self, soup) -> str:
        links = soup.find_all("a")
        for link in links:
            if isinstance(link, Tag) and "href" in link.attrs:
                href = link["href"]
                if isinstance(href, str) and href.startswith("/artist"):
                    return link.text
        raise ValueError("Artist name not found")

    def _extract_text(self, link: Tag) -> str:
        if isinstance(link.text, str):
            return link.text
        raise ValueError("Link text not found or not a string")

    def _extract_title(self, link: Tag, artist_name: str) -> str:
        text = self._extract_text(link)
        return f"{artist_name} - {text}"

    def _extract_link(self, link: Tag) -> str:
        href = link.get("href")
        if isinstance(href, str) and href.startswith("/album"):
            return f"https://open.spotify.com{href}"
        raise ValueError("Link href not found or not valid")

    @property
    async def _artist_name(self) -> str:
        soup = await self._get_discography_soup()
        return await self._parse_artist_name(soup)
