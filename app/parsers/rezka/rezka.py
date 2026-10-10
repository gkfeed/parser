import asyncio
import re
from datetime import timedelta
from enum import Enum, auto
from functools import cached_property
from typing import override
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Tag

from app.extensions.parsers.exceptions import UnavailableFeed
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.extensions.parsers.selenium import SeleniumParserExtension


class RezkaPageMode(Enum):
    FILM = auto()
    SERIES = auto()


class RezkaPageUnavailable(UnavailableFeed):
    def __init__(self, url: str, reason: str) -> None:
        super().__init__(url)
        self.reason = reason

    def __str__(self) -> str:
        return f"Could not load Rezka page {self.url}: {self.reason}"


class RezkaFeed(PostToItemsMixin, ItemsHashExtension, SeleniumParserExtension):
    _selenium_wait_time = 5
    _show_page: tuple[Tag, str] | None = None

    @override
    async def get_html(self, url: str, *, attempts: int = 3) -> bytes:
        if self.cache.has_valid_cache(url):
            html = self.cache.get(url)
            if not self._page_error(html):
                return html
            # Discard error pages cached before response validation was added.
            self.cache.set_with_expiry(url, b"", timedelta(0))

        while True:
            html = await super()._fetch_html(url)
            error = self._page_error(html)
            if not error:
                self.cache.set_with_expiry(url, html, self._http_response_storage_time)
                return html
            attempts -= 1
            if attempts <= 0 or not error.startswith(
                ("HTTP ERROR 5", "ERR_", "net::ERR_")
            ):
                raise RezkaPageUnavailable(url, error)
            await asyncio.sleep(2)

    @staticmethod
    def _page_error(html: bytes) -> str | None:
        soup = BeautifulSoup(html, "html.parser")
        error = soup.select_one("body.neterror .error-code, .content .error-code")
        if error:
            return error.get_text(" ", strip=True)
        if soup.select_one("#anubis_challenge"):
            return "Anubis browser challenge"
        return None

    @cached_property
    def _page_mode(self) -> RezkaPageMode:
        if "/films/" in self.feed.url:
            return RezkaPageMode.FILM
        return RezkaPageMode.SERIES

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self._show_soup

        if self._page_mode is RezkaPageMode.FILM:
            h2_tags = soup.find_all("h2")
            if not h2_tags:
                raise ValueError("Could not extract h2 tags: No <h2> tags found")
            last_h2 = h2_tags[-1]
            if not isinstance(last_h2, Tag):
                raise ValueError("Last h2 is not a Tag")
            return [last_h2]

        active_season = soup.select_one(".b-simple_season__item.active")
        tab_id = active_season.get("data-tab_id") if active_season else "1"
        tab_id = str(tab_id) if tab_id else "1"
        return self._extract_episodes(soup, tab_id)

    @override
    async def _get_post_title(self, post: Tag) -> str:
        if self._page_mode is RezkaPageMode.FILM:
            return post.text

        soup = await self._show_soup
        title = self._extract_title(soup)
        active_season = soup.select_one(".b-simple_season__item.active")
        season_text = active_season.text if active_season else "1 Сезон"
        return f"{title} {season_text} {post.text}"

    @override
    async def _get_post_text(self, post: Tag) -> str:
        return post.text

    @override
    async def _get_post_link(self, post: Tag) -> str:
        return self._show_page[1] if self._show_page else self.feed.url

    @property
    async def _show_soup(self) -> Tag:
        if self._show_page is not None:
            return self._show_page[0]

        show_id = urlsplit(self.feed.url).path.rsplit("/", 1)[-1].split("-", 1)[0]
        soup: Tag | None = None
        link = self.feed.url
        unavailable: RezkaPageUnavailable | None = None
        for index, url in enumerate(self._show_urls):
            try:
                html = await self.get_html(url, attempts=3 if index == 0 else 1)
            except RezkaPageUnavailable as exc:
                if not exc.reason.startswith(("HTTP ERROR 5", "HTTP ERROR 404")):
                    raise
                unavailable = unavailable or exc
                continue
            page = BeautifulSoup(html, "html.parser")
            heading = page.select_one(".b-post__title h1")
            episodes = page.select_one(".b-simple_episode__item")
            if index == 0:
                soup = page
                if self._page_mode is RezkaPageMode.FILM or episodes or not heading:
                    break
            elif (
                heading and episodes and page.select_one(f'#post_id[value="{show_id}"]')
            ):
                soup, link = page, url
                break

        if soup is None:
            assert unavailable is not None
            raise unavailable
        self._show_page = soup, link
        return soup

    @cached_property
    def _show_urls(self) -> list[str]:
        parts = urlsplit(self.feed.url)._replace(netloc="hdrezka.me")
        match = re.fullmatch(
            r"(.*/\d+-.+)-(\d{4})(?:-(?:u|latest))?\.html",
            parts.path,
        )
        if self._page_mode is RezkaPageMode.FILM or match is None:
            return [parts.geturl()]
        prefix, year = match.groups()
        paths = [parts.path, f"{prefix}-{year}-u.html", f"{prefix}-{year}-latest.html"]
        if not prefix.endswith("-serial"):
            paths.append(f"{prefix}-serial-{year}-latest.html")
        return [parts._replace(path=path).geturl() for path in dict.fromkeys(paths)]

    def _extract_title(self, soup: Tag) -> str:
        title_tag = soup.find("h1")
        if not (title_tag and isinstance(title_tag, Tag)):
            raise ValueError(
                "Could not extract title: <h1> tag not found or not a Tag instance."
            )
        return title_tag.text

    def _extract_episodes(self, soup: Tag, tab_id: str) -> list[Tag]:
        container = soup.find(id=f"simple-episodes-list-{tab_id}")
        if not container or not isinstance(container, Tag):
            raise ValueError(
                f"Could not extract episodes container for tab_id {tab_id}"
            )
        return [
            a
            for a in container.find_all(class_="b-simple_episode__item")
            if isinstance(a, Tag)
        ]
