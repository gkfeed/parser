from datetime import UTC, datetime, timedelta
from typing import override
from urllib.parse import urljoin

from bs4 import Tag

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
    _source_url = "https://livesball.ru/"

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self._source_url)

        top_match_container = soup.select_one(".lb-top-matches")
        if top_match_container is None:
            raise FeedUnavailable(self._source_url, "missing_content")

        return top_match_container.select("a.lb-match-card")

    @override
    async def _get_post_title(self, post: Tag) -> str:
        league_name = self._extract_league_name(post)
        team1, team2 = self._extract_teams(post)
        return f"{team1} vs {team2} - {league_name}"

    @override
    async def _get_post_link(self, post: Tag) -> str:
        match_url = required_attr(post, "href", "Liveball match link")
        return urljoin(self._base_url, match_url)

    @override
    async def _get_post_datetime(self, post: Tag) -> datetime:
        timestamp_str = post.get("data-target")
        if not timestamp_str:
            return await super()._get_post_datetime(post)

        timestamp = int(str(timestamp_str)) / 1000
        return datetime.fromtimestamp(timestamp, tz=UTC)

    def _extract_league_name(self, match: Tag) -> str:
        league_elem = require_tag(
            match.select_one(".lb-match-card__tournament"), "Liveball tournament"
        )
        return required_text(league_elem, "Liveball tournament")

    def _extract_teams(self, match: Tag) -> tuple[str, str]:
        teams = match.select(".lb-match-team__name")
        if len(teams) != 2:
            raise ValueError("Expected two team names")

        team1, team2 = (team.get_text(strip=True) for team in teams)
        if not team1 or not team2:
            raise ValueError("Team name not found")

        return team1, team2
