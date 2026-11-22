from datetime import UTC, datetime
from typing import override
from urllib.parse import urljoin

import structlog
from bs4 import BeautifulSoup, Tag
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.exceptions import FeedUnavailable
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.utils.html import require_tag, required_attr, required_text
from app.utils.logging import url_log_fields

logger = structlog.get_logger(__name__)


class HltvFeed(
    PostToItemsMixin, ItemsHashExtension, SeleniumParserExtension, CacheFeedExtension
):
    @staticmethod
    def _is_challenge(html: bytes) -> bool:
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(strip=True).lower() if soup.title else ""
        return (
            title.startswith("just a moment")
            or soup.select_one("#challenge-running, #challenge-form") is not None
        )

    @override
    def _validate_html(self, url: str, html: bytes) -> None:
        if self._is_challenge(html):
            raise FeedUnavailable(url, "cloudflare_challenge")
        soup = BeautifulSoup(html, "html.parser")
        if soup.select_one("body.neterror, #main-frame-error") is not None:
            raise FeedUnavailable(url, "browser_load_error")
        title = soup.title.get_text(strip=True).lower() if soup.title else ""
        if title.startswith(("access denied", "attention required")):
            raise FeedUnavailable(url, "source_blocked")

    @override
    def make_actions(self, driver: WebDriver) -> None:
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        (
                            "//h2[contains(@class, 'standard-headline') and "
                            "starts-with(normalize-space(.), 'Upcoming matches for')]"
                        ),
                    )
                )
            )
        except TimeoutException as exc:
            try:
                self._validate_html(self.feed.url, driver.page_source.encode())
            except FeedUnavailable as unavailable:
                raise unavailable from exc
            reason = "upcoming_headline_timeout"
            logger.warning(
                "hltv_page_unavailable", **url_log_fields(self.feed.url), reason=reason
            )
            raise FeedUnavailable(self.feed.url, reason) from exc

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)

        def is_upcoming_matches_headline(tag: Tag) -> bool:
            return (
                tag.name == "h2"
                and "standard-headline" in (tag.get("class") or [])
                and tag.get_text(" ", strip=True).startswith("Upcoming matches for")
            )

        upcoming_matches_headline_tag = soup.find(is_upcoming_matches_headline)

        if upcoming_matches_headline_tag is None:
            raise ValueError("Upcoming matches headline not found.")

        headline_container = upcoming_matches_headline_tag
        if isinstance(
            upcoming_matches_headline_tag.parent, Tag
        ) and "headline-with-action" in (
            upcoming_matches_headline_tag.parent.get("class") or []
        ):
            headline_container = upcoming_matches_headline_tag.parent

        # HLTV now wraps the table in a profile box. Stay in the adjacent
        # section so a missing schedule cannot select the past-results table.
        section = headline_container.find_next_sibling()
        match_table = None
        if isinstance(section, Tag) and "profile-box" in (section.get("class") or []):
            match_table = section.select_one("table.table-container.match-table")
            empty_state = section.select_one(".empty-state")
            team = upcoming_matches_headline_tag.get_text(" ", strip=True).removeprefix(
                "Upcoming matches for "
            )
            if (
                match_table is None
                and empty_state is not None
                and (
                    empty_state.get_text(" ", strip=True)
                    == f"No upcoming matches for {team}, check back later."
                )
            ):
                return []

        if not isinstance(match_table, Tag):
            logger.warning(
                "hltv_match_section_invalid",
                **url_log_fields(self.feed.url),
                reason="missing_match_table",
                section_tag=section.name if isinstance(section, Tag) else None,
                match_tables=len(soup.select("table.match-table")),
            )
            raise ValueError(  # noqa: TRY004 - missing page data is a value error
                "Upcoming match table not found or invalid."
            )

        rows = [
            row
            for row in match_table.find_all("tr", class_="team-row")
            if isinstance(row, Tag)
        ]
        if not rows:
            raise ValueError("Upcoming match table has no match rows.")
        return rows

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
        match_link_tag = require_tag(
            post.select_one(
                "td.matchpage-button-cell a[href], td.stats-button-cell a[href]"
            ),
            "HLTV match link",
        )
        href = required_attr(match_link_tag, "href", "HLTV match link")
        return urljoin("https://www.hltv.org", href)

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

        return (
            required_text(team1_name_tag, "HLTV first team name"),
            required_text(team2_name_tag, "HLTV second team name"),
        )
