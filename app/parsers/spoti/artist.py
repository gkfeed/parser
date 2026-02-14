from datetime import timedelta
from bs4.element import Tag

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.extensions.parsers.hash import ItemsHashExtension

from app.serializers.feed import Item
from app.utils.datetime import constant_datetime


class SpotifyFeed(SeleniumParserExtension, CacheFeedExtension, ItemsHashExtension):
    _cache_storage_time = timedelta(days=1)
    _selenium_wait_time = 20

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
        _url = self.feed.url
        if _url.endswith("/"):
            _url = _url[:-1]

        soup = await self.get_soup(_url + "/discography")
        if soup.title and "Page not found" in soup.title.text:
            return await self.get_soup(_url)
        return soup

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
        meta_title = soup.find("meta", property="og:title")
        if meta_title and isinstance(meta_title, Tag) and meta_title.get("content"):
            return meta_title["content"]

        h1 = soup.find("h1")
        if h1 and h1.text and h1.text != "Your Library":
            return h1.text

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
