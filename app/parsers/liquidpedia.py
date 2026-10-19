from datetime import UTC, datetime
from typing import ClassVar, override
from urllib.parse import (
    parse_qs,
    unquote,
    urljoin,
    urlsplit,
)

from bs4 import BeautifulSoup, Tag

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.services.liquidpedia import LiquidpediaClient, get_page_title


class LiquidpediaFeed(
    PostToItemsMixin, ItemsHashExtension, HttpParserExtension, CacheFeedExtension
):
    _headers: ClassVar[dict[str, str]] = LiquidpediaClient.headers

    @property
    @override
    async def _posts(self) -> list[Tag]:
        html = await LiquidpediaClient(self.get_html).get_page_html(self.feed.url)
        soup = BeautifulSoup(html, "html.parser")
        matches = self._get_upcoming_matches(soup)
        if matches:
            return matches

        # Team pages without scheduled matches omit the Upcoming Matches
        # heading. Their recent matches are rendered using table2 markup. The
        # rows are not guaranteed to be ``tr`` elements, so select the row
        # class independently of the element name.
        return list(soup.select(".match-table-wrapper .table2__row--body"))

    @staticmethod
    def _get_upcoming_matches(soup: BeautifulSoup) -> list[Tag]:
        heading = soup.find(id="Upcoming_Matches")
        if not isinstance(heading, Tag) or not isinstance(heading.parent, Tag):
            return []

        container = heading.parent.find_next_sibling()
        if not isinstance(container, Tag):
            return []

        return list(container.select(".match-info"))

    @override
    async def _get_post_title(self, post: Tag) -> str:
        team_names: list[str] = []
        for opponent in post.select(".match-info-opponent-row"):
            name_tag = opponent.select_one(".name, .brkts-opponent-block-literal")
            if not isinstance(name_tag, Tag):
                raise ValueError(  # noqa: TRY004 - missing page data is a value error
                    "Team name not found"
                )
            team_names.append(name_tag.get_text(" ", strip=True))

        if not team_names:
            team_names = [
                name_tag.get_text(" ", strip=True)
                for name_tag in post.select(".block-team .name")
                if isinstance(name_tag, Tag)
            ]
            if len(team_names) == 1:
                team_names.insert(0, self._get_team_name_from_url())

        if len(team_names) != 2 or not all(team_names):
            raise ValueError("Expected two team names")

        return " vs ".join(team_names)

    @override
    async def _get_post_link(self, post: Tag) -> str:
        for link_tag in post.select("a[href]"):
            href = link_tag.get("href")
            if not isinstance(href, str):
                continue

            link = urljoin(self.feed.url, href)
            url = urlsplit(link)
            page = unquote(url.path.rstrip("/").rsplit("/", 1)[-1])
            if page.startswith("Match:"):
                return link

            title = parse_qs(url.query).get("title", [""])[0]
            if title.startswith("Match:"):
                return link

        tournament_link = post.select_one(".match-info-tournament-name a[href]")
        if tournament_link:
            href = tournament_link.get("href")
            if isinstance(href, str):
                return urljoin(self.feed.url, href)

        classes = post.get("class")
        if isinstance(classes, list) and "table2__row--body" in classes:
            # Recent-match rows do not always link to a dedicated match page.
            return self.feed.url

        raise ValueError("Match page link not found")

    @override
    async def _get_post_datetime(self, post: Tag) -> datetime:
        timestamp_value: object = post.get("data-timestamp")
        if not isinstance(timestamp_value, (str, int)):
            timestamp_tag = post.select_one("[data-timestamp]")
            timestamp_value = (
                timestamp_tag.get("data-timestamp") if timestamp_tag else None
            )

        if isinstance(timestamp_value, (str, int)):
            return self._parse_timestamp(timestamp_value)

        time_tag = post.select_one("time[datetime]")
        datetime_value = time_tag.get("datetime") if time_tag else None
        if isinstance(datetime_value, str):
            return self._parse_iso_datetime(datetime_value)

        raise ValueError("Match timestamp not found")

    @staticmethod
    def _parse_timestamp(value: str | int) -> datetime:
        """Parse Unix timestamps represented in seconds or milliseconds."""

        try:
            timestamp = int(value)
        except ValueError as error:
            raise ValueError("Invalid match timestamp") from error

        # Some table variants expose Unix time in milliseconds.
        if abs(timestamp) >= 100_000_000_000:
            timestamp //= 1_000

        try:
            return datetime.fromtimestamp(timestamp, UTC)
        except (OverflowError, OSError, ValueError) as error:
            raise ValueError("Invalid match timestamp") from error

    @staticmethod
    def _parse_iso_datetime(value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as error:
            raise ValueError("Invalid datetime attribute") from error

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _get_team_name_from_url(self) -> str:
        url = urlsplit(self.feed.url)
        page = url.path.rstrip("/").rsplit("/", 1)[-1]
        page = get_page_title(url, page)
        team_name = page.replace("_", " ").strip()
        if not team_name:
            raise ValueError("Could not extract team name from Liquipedia URL")
        return team_name
