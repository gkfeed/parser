from datetime import UTC, datetime, timedelta
from typing import override
from urllib.parse import urljoin

import structlog
from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.exceptions import UnavailableFeed
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.extensions.parsers.selenium import SeleniumParserExtension

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
    async def get_html(self, url: str) -> bytes:
        if self.cache.has_valid_cache(url):
            html = self.cache.get(url)
            if not self._is_challenge(html):
                return html
            # Discard challenges cached by older versions and try a fresh page.
            self.cache.set_with_expiry(url, html, timedelta(0))

        return await super().get_html(url)

    @override
    async def _fetch_html(self, url: str) -> bytes:
        html = await super()._fetch_html(url)
        if self._is_challenge(html):
            raise UnavailableFeed(url)
        return html

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
            reason = (
                "cloudflare_challenge"
                if self._is_challenge(driver.page_source.encode())
                else "upcoming_headline_timeout"
            )
            logger.warning("hltv_page_unavailable", url=self.feed.url, reason=reason)
            raise UnavailableFeed(self.feed.url) from exc

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
