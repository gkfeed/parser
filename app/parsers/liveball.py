from datetime import timedelta, datetime, timezone
from typing import override

from bs4 import Tag

from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin


class LiveballFeed(PostToItemsMixin, HttpParserExtension, CacheFeedExtension):
    _cache_storage_time = timedelta(hours=1)
    _base_url = "https://liveball.my"

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)

        top_match_container = soup.find("section", class_="top_match_section")
        if not top_match_container or not isinstance(top_match_container, Tag):
            return []

        return [
            m
            for m in top_match_container.select("div.top_match div.league_block")
            if isinstance(m, Tag)
        ]

    @override
    async def _get_post_title(self, post: Tag) -> str:
        league_name = self._extract_league_name(post)
        team1, team2 = self._extract_teams(post)
        return f"{team1} vs {team2} - {league_name}"

    @override
    async def _get_post_link(self, post: Tag) -> str:
        link_elem = post.select_one("a.la")
        if not link_elem:
            raise ValueError("Match URL element not found")

        match_url = link_elem.get("href")
        if not match_url:
            raise ValueError("Match URL not found")

        match_url = str(match_url)
        if not match_url.startswith("http"):
            match_url = self._base_url + match_url
        return match_url

    @override
    async def _get_post_datetime(self, post: Tag) -> datetime:
        timer_elem = post.select_one(".tm_timer")
        if not timer_elem:
            return await super()._get_post_datetime(post)

        timestamp_str = timer_elem.get("value")
        if not timestamp_str:
            return await super()._get_post_datetime(post)

        timestamp = int(str(timestamp_str))
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)

    def _extract_league_name(self, match: Tag) -> str:
        league_elem = match.select_one(".tm_league_name")
        if league_elem:
            return league_elem.get_text(strip=True)
        raise ValueError("League name not found")

    def _extract_teams(self, match: Tag) -> tuple[str | None, str | None]:
        team1_elem = match.select_one(".t_left .league_title")
        team2_elem = match.select_one(".t_right .league_title")
        team1 = team1_elem.get_text(strip=True) if team1_elem else None
        team2 = team2_elem.get_text(strip=True) if team2_elem else None
        return team1, team2
