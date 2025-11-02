from datetime import datetime
from urllib.parse import urlparse
from typing import Optional

from bs4 import Tag
from bs4.element import NavigableString

from app.extensions.parsers.http import HttpParserExtension
from app.extensions.hash import ItemsHashExtension
from app.extensions.cache import CacheFeedExtension
from app.serializers.feed import Item


class HltvFeed(ItemsHashExtension, HttpParserExtension, CacheFeedExtension):
    @property
    async def items(self) -> list[Item]:
        soup = await self.get_soup(self.feed.url)

        def is_upcoming_matches_headline(tag: Tag) -> bool:
            if tag.name != "h2":
                return False

            classes = tag.get("class")
            if not classes or "standard-headline" not in classes:
                return False

            return isinstance(
                tag.string, NavigableString
            ) and tag.string.strip().startswith("Upcoming matches for")

        upcoming_matches_headlines = soup.find_all(
            is_upcoming_matches_headline, limit=1
        )
        upcoming_matches_headline_tag = (
            upcoming_matches_headlines[0] if upcoming_matches_headlines else None
        )

        if not upcoming_matches_headline_tag:
            raise ValueError("Upcoming matches headline not found.")

        match_table = upcoming_matches_headline_tag.find_next_sibling(
            "table", class_="table-container match-table"
        )

        if not isinstance(match_table, Tag):
            raise ValueError("Match table not found or invalid.")

        items = []
        for row in match_table.find_all("tr", class_="team-row"):
            if isinstance(row, Tag):
                item = self._parse_match_row(row)
                if item:
                    items.append(item)
        return items

    def _parse_match_row(self, row: Tag) -> Optional[Item]:
        try:
            date = self._extract_match_date(row)
            teams = self._extract_teams(row)
            if not teams:
                return None
            team1_name, team2_name = teams
            link = self._extract_match_link(row)

            if not date or not team1_name or not team2_name or not link:
                return None

            return Item(
                title=f"{team1_name} vs {team2_name}",
                text=f"Upcoming match: {team1_name} vs {team2_name}",
                date=date,
                link=link,
            )
        except (ValueError, IndexError):
            return None

    def _extract_match_date(self, row: Tag) -> Optional[datetime]:
        date_cell = row.find("td", class_="date-cell")
        if not isinstance(date_cell, Tag):
            return None

        unix_timestamp_ms_tag = date_cell.find("span")
        if not isinstance(
            unix_timestamp_ms_tag, Tag
        ) or not unix_timestamp_ms_tag.has_attr("data-unix"):
            return None

        unix_timestamp = int(str(unix_timestamp_ms_tag["data-unix"])) / 1000
        return datetime.fromtimestamp(unix_timestamp)

    def _extract_teams(self, row: Tag) -> Optional[tuple[str, str]]:
        team_center_cell = row.find("td", class_="team-center-cell")
        if not isinstance(team_center_cell, Tag):
            return None

        teams = team_center_cell.find_all("div", class_="team-flex")
        if len(teams) != 2:
            return None

        team1_div, team2_div = teams
        if not isinstance(team1_div, Tag) or not isinstance(team2_div, Tag):
            return None

        team1_name_tag = team1_div.find("a", class_="team-name")
        team2_name_tag = team2_div.find("a", class_="team-name")

        if not isinstance(team1_name_tag, Tag) or not isinstance(team2_name_tag, Tag):
            return None

        return team1_name_tag.text, team2_name_tag.text

    def _extract_match_link(self, row: Tag) -> Optional[str]:
        matchpage_button_cell = row.find("td", class_="matchpage-button-cell")
        if not isinstance(matchpage_button_cell, Tag):
            return None

        match_link_tag = matchpage_button_cell.find("a")
        if not isinstance(match_link_tag, Tag) or not match_link_tag.has_attr("href"):
            return None

        return "https://www.hltv.org" + str(match_link_tag["href"])

    @property
    def _team_id(self) -> str:
        return self._parsed_url.path.split("/")[2]

    @property
    def _team_name(self) -> str:
        return self._parsed_url.path.split("/")[3]

    @property
    def _parsed_url(self):
        return urlparse(self.feed.url)
