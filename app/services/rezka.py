import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum, auto
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Tag

from app.extensions.parsers.exceptions import FeedUnavailable


class RezkaPageMode(Enum):
    FILM = auto()
    SERIES = auto()


class RezkaPageUnavailable(FeedUnavailable):
    def __str__(self) -> str:
        return f"Could not load Rezka page {self.url}: {self.reason}"


def _required_text(tag: Tag | None, field: str) -> str:
    if tag is None or not (text := tag.get_text().strip()):
        raise ValueError(f"Missing or empty Rezka {field}")
    return text


@dataclass(frozen=True)
class RezkaPage:
    soup: Tag
    url: str
    title: str
    season: str
    posts: list[Tag]


class RezkaClient:
    """Resolve Rezka cards using the caller's cached HTML/browser lifecycle."""

    def __init__(self, fetch: Callable[[str], Awaitable[bytes]]) -> None:
        self._fetch = fetch

    async def get_html(self, url: str, *, attempts: int = 3) -> bytes:
        while True:
            html = await self._get_html_attempt(url, attempts=attempts)
            if html is not None:
                return html
            attempts -= 1
            await asyncio.sleep(2)

    async def _get_html_attempt(self, url: str, *, attempts: int) -> bytes | None:
        """Return None only when a transient page error permits another attempt."""
        try:
            html = await self._fetch(url)
            self._validate_browser_page(url, BeautifulSoup(html, "html.parser"))
            return html
        except RezkaPageUnavailable as exc:
            if attempts <= 1 or not exc.reason.startswith(
                ("HTTP ERROR 5", "ERR_", "net::ERR_")
            ):
                raise
            return None

    async def resolve(self, url: str, mode: RezkaPageMode) -> RezkaPage:
        failures: list[str] = []
        last_error: RezkaPageUnavailable | None = None
        for index, candidate in enumerate(self.show_urls(url, mode)):
            try:
                html = await self.get_html(candidate, attempts=3 if index == 0 else 1)
                page = self.parse_page(candidate, html, mode)
            except RezkaPageUnavailable as exc:
                last_error = exc
                failures.append(f"{candidate}: {exc.reason}")
                continue
            # Preserve the subscribed URL for a valid primary, including mirrors.
            link = url if index == 0 else candidate
            return RezkaPage(page.soup, link, page.title, page.season, page.posts)

        raise RezkaPageUnavailable(
            url, "No usable Rezka source; " + "; ".join(failures)
        ) from last_error

    @staticmethod
    def show_urls(url: str, mode: RezkaPageMode) -> list[str]:
        parts = urlsplit(url)._replace(netloc="hdrezka.me")
        match = re.fullmatch(r"(.*/\d+-.+)-(\d{4})(?:-(?:u|latest))?\.html", parts.path)
        if match is None:
            return [parts.geturl()]
        prefix, year = match.groups()
        if mode is RezkaPageMode.FILM:
            # Moved films can return HTTP 500 at the old URL in a fresh session.
            paths = [parts.path, f"{prefix}-{year}-latest.html"]
            return [parts._replace(path=path).geturl() for path in dict.fromkeys(paths)]
        paths = [parts.path, f"{prefix}-{year}-u.html", f"{prefix}-{year}-latest.html"]
        if not prefix.endswith("-serial"):
            paths.append(f"{prefix}-serial-{year}-latest.html")
        return [parts._replace(path=path).geturl() for path in dict.fromkeys(paths)]

    @staticmethod
    def _show_id(url: str) -> str | None:
        match = re.match(r"(\d+)-", urlsplit(url).path.rsplit("/", 1)[-1])
        return match[1] if match else None

    @classmethod
    def validate_html(cls, url: str, html: bytes, mode: RezkaPageMode) -> None:
        soup = BeautifulSoup(html, "html.parser")
        cls._validate_browser_page(url, soup)
        # Only card URLs carry a show ID; check browser errors for every URL.
        if cls._show_id(url) is not None:
            cls.parse_page(url, html, mode)

    @staticmethod
    def _validate_browser_page(url: str, soup: Tag) -> None:
        error = soup.select_one("body.neterror .error-code, .content .error-code")
        if error is not None:
            reason = error.get_text(" ", strip=True) or "Empty browser error page"
            raise RezkaPageUnavailable(url, reason)
        if soup.select_one("#anubis_challenge") is not None:
            raise RezkaPageUnavailable(url, "Anubis browser challenge")

    @classmethod
    def parse_page(cls, url: str, html: bytes, mode: RezkaPageMode) -> RezkaPage:
        soup = BeautifulSoup(html, "html.parser")
        cls._validate_browser_page(url, soup)
        try:
            cls._validate_identity(url, soup)
            # Older cards have a bare h1 instead of the b-post__title wrapper.
            heading = soup.select_one(".b-post__title h1")
            if heading is None:
                heading = soup.select_one("h1")
            title = _required_text(heading, "title")
            if mode is RezkaPageMode.FILM:
                status = soup.select_one(".b-post__lastepisodeout h2")
                _required_text(status, "film title/status")
                assert status is not None
                return RezkaPage(soup, url, title, "", [status])
            return cls._series_page(soup, url, title)
        except ValueError as exc:
            raise RezkaPageUnavailable(url, str(exc)) from exc

    @classmethod
    def _validate_identity(cls, url: str, soup: Tag) -> None:
        show_id = cls._show_id(url)
        if show_id is None:
            raise ValueError("Cannot determine Rezka show ID from URL")
        identities: list[str | None] = []
        post_id = soup.select_one("#post_id")
        if post_id is not None:
            identities.append(str(post_id.get("value") or ""))
        # Legacy cards can identify themselves through their canonical URL.
        for identity in soup.select('link[rel="canonical"], meta[property="og:url"]'):
            identity_url = str(identity.get("href") or identity.get("content") or "")
            identities.append(cls._show_id(identity_url))
        if not identities or any(value != show_id for value in identities):
            raise ValueError(f"Missing or mismatched Rezka identity for show {show_id}")

    @staticmethod
    def _is_waiting_for_series(soup: Tag) -> bool:
        status = soup.select_one("#player .b-post__go_status")
        if status is None:
            return False
        # Trailer-only cards explicitly state that the series is not available.
        text = status.get_text(" ", strip=True)
        return text == "Ожидаем сериал в хорошем качестве..."

    @staticmethod
    def _series_page(soup: Tag, url: str, title: str) -> RezkaPage:
        has_episodes = soup.select_one(".b-simple_episode__item") is not None
        if not has_episodes and RezkaClient._is_waiting_for_series(soup):
            return RezkaPage(soup, url, title, "", [])
        active_season = soup.select_one(".b-simple_season__item.active")
        season = "1 Сезон"
        tab_id = "1"
        if active_season is not None:
            season = _required_text(active_season, "season title")
            tab_id = str(active_season.get("data-tab_id") or "").strip()
            if not tab_id:
                raise ValueError("Missing Rezka active season tab ID")
        container = soup.find(id=f"simple-episodes-list-{tab_id}")
        if not isinstance(container, Tag):
            raise ValueError(  # noqa: TRY004 - missing source markup is invalid data
                f"Missing Rezka episodes container for tab_id {tab_id}"
            )
        posts = list(container.select(".b-simple_episode__item"))
        if not posts:
            raise ValueError(f"Empty Rezka episodes container for tab_id {tab_id}")
        for post in posts:
            _required_text(post, "episode title/status")
        return RezkaPage(soup, url, title, season, posts)
