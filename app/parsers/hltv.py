from datetime import datetime
from typing import override, Optional

from bs4 import Tag
from bs4.element import NavigableString

from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.serializers.feed import Item


class HltvFeed(PostToItemsMixin, ItemsHashExtension, HttpParserExtension, CacheFeedExtension):
    @property
    @override
    async def _posts(self) -> list[Tag]:
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

        return [
            row
            for row in match_table.find_all("tr", class_="team-row")
            if isinstance(row, Tag)
        ]

    @property
    @override
    async def items(self) -> list[Item]:
        # Hltv has try-except logic per row in old implementation, we can override items to replicate it
        # or just implement _get_post methods and let mixin handle it.
        # The old implementation skipped rows that failed to parse.
        items = []
        for p in await self._posts:
            try:
                items.append(
                    Item(
                        title=await self._get_post_title(p),
                        text=await self._get_post_text(p),
                        date=await self._get_post_datetime(p),
                        link=await self._get_post_link(p),
                    )
                )
            except (ValueError, IndexError):
                continue
        return items

    @override
    async def _get_post_title(self, post: Tag) -> str:
        teams = self._extract_teams(post)
        if not teams:
            raise ValueError("Teams not found")
        team1_name, team2_name = teams
        return f"{team1_name} vs {team2_name}"

    @override
    async def _get_post_text(self, post: Tag) -> str:
        title = await self._get_post_title(post)
        return f"Upcoming match: {title}"

    @override
    async def _get_post_link(self, post: Tag) -> str:
        matchpage_button_cell = post.find("td", class_="matchpage-button-cell")
        if not isinstance(matchpage_button_cell, Tag):
            raise ValueError("Link cell not found")

        match_link_tag = matchpage_button_cell.find("a")
        if not isinstance(match_link_tag, Tag) or not match_link_tag.has_attr("href"):
            raise ValueError("Link tag not found")

        return "https://www.hltv.org" + str(match_link_tag["href"])

    @override
    async def _get_post_datetime(self, post: Tag) -> datetime:
        date_cell = post.find("td", class_="date-cell")
        if not isinstance(date_cell, Tag):
            raise ValueError("Date cell not found")

        unix_timestamp_ms_tag = date_cell.find("span")
        if not isinstance(
            unix_timestamp_ms_tag, Tag
        ) or not unix_timestamp_ms_tag.has_attr("data-unix"):
            raise ValueError("Timestamp tag not found")

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
