from datetime import UTC, datetime
from typing import override
from urllib.parse import urljoin

from bs4 import Tag
from bs4.element import NavigableString

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.serializers.feed import Item


class HltvFeed(
    PostToItemsMixin, ItemsHashExtension, SeleniumParserExtension, CacheFeedExtension
):
    _selenium_wait_time = 10

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)

        def is_upcoming_matches_headline(tag: Tag) -> bool:
            return (
                tag.name == "h2"
                and "standard-headline" in (tag.get("class") or [])
                and isinstance(tag.string, NavigableString)
                and tag.string.strip().startswith("Upcoming matches for")
            )

        upcoming_matches_headline_tag = soup.find(is_upcoming_matches_headline)

        if upcoming_matches_headline_tag is None:
            raise ValueError("Upcoming matches headline not found.")

        headline_container = upcoming_matches_headline_tag
        if (
            isinstance(upcoming_matches_headline_tag.parent, Tag)
            and "headline-with-action"
            in (upcoming_matches_headline_tag.parent.get("class") or [])
        ):
            headline_container = upcoming_matches_headline_tag.parent

        match_table = headline_container.find_next_sibling(
            "table", class_="table-container match-table"
        )

        if not isinstance(match_table, Tag):
            raise ValueError(  # noqa: TRY004 - missing page data is a value error
                "Match table not found or invalid."
            )

        return [
            row
            for row in match_table.find_all("tr", class_="team-row")
            if isinstance(row, Tag)
        ]

    @property
    @override
    async def items(self) -> list[Item]:
        # One malformed match should not abort the entire feed.
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
        match_link_tag = post.select_one(
            "td.matchpage-button-cell a[href], td.stats-button-cell a[href]"
        )
        if not isinstance(match_link_tag, Tag):
            raise ValueError(  # noqa: TRY004 - missing page data is a value error
                "Link tag not found"
            )

        return urljoin("https://www.hltv.org", str(match_link_tag["href"]))

    @override
    async def _get_post_datetime(self, post: Tag) -> datetime:
        date_cell = post.find("td", class_="date-cell")
        if not isinstance(date_cell, Tag):
            raise ValueError(  # noqa: TRY004 - missing page data is a value error
                "Date cell not found"
            )

        unix_timestamp_ms_tag = date_cell.find("span")
        if not isinstance(
            unix_timestamp_ms_tag, Tag
        ) or not unix_timestamp_ms_tag.has_attr("data-unix"):
            raise ValueError("Timestamp tag not found")

        unix_timestamp = int(str(unix_timestamp_ms_tag["data-unix"])) / 1000
        return datetime.fromtimestamp(unix_timestamp, UTC)

    def _extract_teams(self, row: Tag) -> tuple[str, str] | None:
        team_center_cell = row.find("td", class_="team-center-cell")
        if not isinstance(team_center_cell, Tag):
            return None

        teams = team_center_cell.find_all("div", class_="team-flex")
        if len(teams) != 2:
            return None

        team1_div, team2_div = teams
        if not isinstance(team1_div, Tag) or not isinstance(team2_div, Tag):
            return None

        team1_name_tag = team1_div.find(class_="team-name")
        team2_name_tag = team2_div.find(class_="team-name")

        if not isinstance(team1_name_tag, Tag) or not isinstance(team2_name_tag, Tag):
            return None

        return team1_name_tag.get_text(strip=True), team2_name_tag.get_text(strip=True)
