import json
from base64 import b64decode
from datetime import timedelta
from typing import override

from bs4 import BeautifulSoup
from bs4.element import Tag

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.serializers.feed import Item
from app.utils.datetime import constant_datetime
from app.utils.html import required_attr, required_text


class SpotifyFeed(SeleniumParserExtension, CacheFeedExtension, ItemsHashExtension):
    _cache_storage_time = timedelta(days=1)
    _selenium_wait_time = 20

    @override
    def _validate_html(self, url: str, html: bytes) -> None:
        soup = BeautifulSoup(html, "html.parser")
        discography_url = self.feed.url.removesuffix("/") + "/discography"
        if (
            url == discography_url
            and soup.title
            and "Page not found" in soup.title.text
        ):
            # Only the discography route may be missing; try the artist root.
            return
        self._extract_release_links(soup)

    def _extract_release_links(self, soup: BeautifulSoup) -> list[Tag]:
        if soup.title and "Page not found" in soup.title.text:
            raise ValueError("Spotify artist page not found")
        page_url = soup.find("meta", property="og:url")
        canonical = soup.find("link", rel="canonical")
        expected_url = self.feed.url.removesuffix("/")
        meta_matches = (
            isinstance(page_url, Tag) and page_url.get("content") == expected_url
        )
        canonical_matches = isinstance(canonical, Tag) and canonical.get("href") in (
            expected_url,
            expected_url + "/discography",
        )
        if not meta_matches and not canonical_matches:
            raise ValueError("Spotify page does not identify the requested artist")
        links = list(soup.select('a[href^="/album"]'))
        if links:
            return links
        if self._has_confirmed_empty_discography(soup):
            return []
        raise ValueError(
            "Spotify releases missing without a confirmed empty discography"
        )

    def _has_confirmed_empty_discography(self, soup: BeautifulSoup) -> bool:
        state_tag = soup.find("script", id="initialState")
        if state_tag is None:
            return False
        # Spotify's artist state lists each release category. Metadata and a
        # missing album selector alone do not prove that the artist is empty.
        artist_id = self.feed.url.removesuffix("/").rsplit("/", maxsplit=1)[-1]
        try:
            state = json.loads(b64decode(state_tag.get_text(strip=True), validate=True))
            artist = state["entities"]["items"][f"spotify:artist:{artist_id}"]
            discography = artist["discography"]
            return (
                artist["__typename"] == "Artist"
                and discography["latest"] is None
                and all(
                    discography[category]["items"] == []
                    for category in (
                        "albums",
                        "singles",
                        "compilations",
                        "popularReleasesAlbums",
                    )
                )
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError("Invalid Spotify artist discography state") from exc

    async def _parse_items(self) -> list[Item]:
        soup = await self._get_discography_soup()
        artist_name = await self._parse_artist_name(soup)
        return [
            Item(
                title=self._extract_title(link, artist_name),
                text=self._extract_text(link),
                date=constant_datetime,
                link=self._extract_link(link),
            )
            for link in await self._parse_releases_links(soup)
        ]

    async def _get_discography_soup(self):
        url = self.feed.url.removesuffix("/")

        soup = await self.get_soup(url + "/discography")
        if soup.title and "Page not found" in soup.title.text:
            return await self.get_soup(url)
        return soup

    async def _parse_releases_links(self, soup) -> list[Tag]:
        return self._extract_release_links(soup)

    async def _parse_artist_name(self, soup) -> str:
        meta_title = soup.find("meta", property="og:title")
        if meta_title and isinstance(meta_title, Tag) and meta_title.get("content"):
            artist_name = required_attr(
                meta_title, "content", "Spotify artist name"
            ).strip()
            if not artist_name:
                raise ValueError("Empty content for Spotify artist name")
            return artist_name

        h1 = soup.find("h1")
        if h1 and h1.text and h1.text != "Your Library":
            return required_text(h1, "Spotify artist name", separator=" ")

        links = soup.find_all("a")
        for link in links:
            if not isinstance(link, Tag):
                continue
            href = link.get("href")
            if not isinstance(href, str) or not href.startswith("/artist"):
                continue
            return required_text(link, "Spotify artist name", separator=" ")
        raise ValueError("Artist name not found")

    def _extract_text(self, link: Tag) -> str:
        return required_text(link, "Spotify release title", separator=" ")

    def _extract_title(self, link: Tag, artist_name: str) -> str:
        text = self._extract_text(link)
        return f"{artist_name} - {text}"

    def _extract_link(self, link: Tag) -> str:
        href = link.get("href")
        if isinstance(href, str) and href.startswith("/album"):
            return f"https://open.spotify.com{href}"
        raise ValueError("Link href not found or not valid")
