from datetime import UTC, datetime, timedelta
from typing import override
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.exceptions import FeedUnavailable
from app.extensions.parsers.hash import ItemIdentityHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.utils.html import require_tag, required_attr, required_text


class LiveballFeed(
    PostToItemsMixin, ItemIdentityHashExtension, HttpParserExtension, CacheFeedExtension
):
    _cache_storage_time = timedelta(hours=1)
    _base_url = "https://liveball.sx"
    _source_url = "https://liveball.sx/"

    @override
    def _validate_html(self, url: str, html: bytes) -> None:
        soup = BeautifulSoup(html, "html.parser")
        match = soup.select_one("a.home-hero")
        if match is None:
            raise FeedUnavailable(url, "missing_content")
        required_attr(match, "href", "Liveball match link")
        self._match_title(match)
        self._match_datetime(match)

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self._source_url)

        match = require_tag(soup.select_one("a.home-hero"), "Liveball top match")
        return [match]

    @override
    async def _get_post_title(self, post: Tag) -> str:
        return self._match_title(post)

    def _match_title(self, post: Tag) -> str:
        league_name = self._extract_league_name(post)
        team1, team2 = self._extract_teams(post)
        return f"{team1} vs {team2} - {league_name}"

    @override
    async def _get_post_link(self, post: Tag) -> str:
        match_url = required_attr(post, "href", "Liveball match link")
        return urljoin(self._base_url, match_url)

    @override
    async def _get_post_datetime(self, post: Tag) -> datetime:
        return self._match_datetime(post) or await super()._get_post_datetime(post)

    @staticmethod
    def _match_datetime(post: Tag) -> datetime | None:
        time_tag = post.select_one('[data-lt="time"][data-ts]')
        if time_tag is None:
            return None

        timestamp = int(required_attr(time_tag, "data-ts", "Liveball match time"))
        return datetime.fromtimestamp(timestamp, tz=UTC)

    def _extract_league_name(self, match: Tag) -> str:
        league_elem = require_tag(
            match.select_one(".home-hero__league"), "Liveball tournament"
        )
        return required_text(league_elem, "Liveball tournament")

    def _extract_teams(self, match: Tag) -> tuple[str, str]:
        teams = match.select(".home-hero__team-name")
        if len(teams) != 2:
            raise ValueError("Expected two team names")

        team1, team2 = (team.get_text(strip=True) for team in teams)
        if not team1 or not team2:
            raise ValueError("Team name not found")

        return team1, team2
