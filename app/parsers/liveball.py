from datetime import datetime, timedelta, timezone

from app.utils.datetime import constant_datetime
from app.serializers.feed import Item
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.cache import CacheFeedExtension


class LiveballFeed(HttpParserExtension, CacheFeedExtension):
    _cache_storage_time = timedelta(hours=1)
    _base_url = "https://liveball.my"

    @property
    async def items(self) -> list[Item]:
        items = []
        soup = await self.get_soup(self.feed.url)

        top_match_container = soup.find("section", class_="top_match_section")
        if not top_match_container:
            return []

        matches = top_match_container.select("div.top_match div.league_block")
        for match in matches:
            if not match or not hasattr(match, "select_one"):
                continue

            league_name = self._extract_league_name(match)
            team1, team2 = self._extract_teams(match)
            match_time = self._extract_match_datetime(match)
            match_url = self._extract_match_url(match)

            items.append(
                Item(
                    title=f"{team1} vs {team2} - {league_name}",
                    text=f"{team1} vs {team2} - {league_name}",
                    date=match_time,
                    link=match_url,
                )
            )

        return items

    def _extract_league_name(self, match) -> str:
        league_elem = match.select_one(".tm_league_name")
        if league_elem:
            return league_elem.get_text(strip=True)
        raise ValueError

    def _extract_teams(self, match) -> tuple[str | None, str | None]:
        team1_elem = match.select_one(".t_left .league_title")
        team2_elem = match.select_one(".t_right .league_title")
        team1 = team1_elem.get_text(strip=True) if team1_elem else None
        team2 = team2_elem.get_text(strip=True) if team2_elem else None
        return team1, team2

    def _extract_match_datetime(self, match) -> datetime:
        timer_elem = match.select_one(".tm_timer")
        if not timer_elem:
            return constant_datetime

        timestamp_str = timer_elem.get("value")
        if not timestamp_str:
            return constant_datetime

        timestamp = int(str(timestamp_str))
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)

    def _extract_match_url(self, match) -> str:
        link_elem = match.select_one("a.la")
        if not link_elem:
            raise ValueError

        match_url = link_elem.get("href")
        if not match_url:
            raise ValueError

        match_url = str(match_url)
        if not match_url.startswith("http"):
            match_url = self._base_url + match_url
        return match_url
