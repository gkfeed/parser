import re
from datetime import datetime, timedelta
from typing import override
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.exceptions import FeedUnavailable
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.serializers.feed import Item
from app.services.hash import HashService
from app.utils.datetime import constant_datetime, parse_datetime
from app.utils.html import require_tag, required_text


class OneFootballFeed(
    PostToItemsMixin, ItemsHashExtension, HttpParserExtension, CacheFeedExtension
):
    __base_url = "https://onefootball.com"
    __match_path = re.compile(r"^/[^/]+/match/\d+/?\Z")
    __entity_title_selector = (
        '[class*="EntityTitle"][class*="__title"], '
        '.xpaLayoutContainerComponentResolver--entityTitle p[class*="_title"]'
    )
    __match_lists_selector = 'ul:is([class*="MatchCardsList"], [class*="_matches"])'
    _cache_storage_time = timedelta(hours=1)

    @override
    def _validate_html(self, url: str, html: bytes) -> None:
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(strip=True).lower() if soup.title else ""
        if title.startswith("just a moment") or soup.select_one(
            "#challenge-form, #challenge-running, #cf-error-details"
        ):
            raise FeedUnavailable(url, "cloudflare_challenge_or_error")

        main = require_tag(soup.find("main"), "OneFootball main content")
        required_text(
            require_tag(
                main.select_one(self.__entity_title_selector),
                "OneFootball entity title",
            ),
            "OneFootball entity title",
        )
        match_lists = main.select(self.__match_lists_selector)
        if not match_lists:
            self._validate_empty_matches(main)
            return

        for match_list in match_lists:
            rows = match_list.select(":scope > li")
            if not rows:
                raise ValueError("Missing OneFootball matches or explicit empty state")
            for row in rows:
                self._match_title(
                    require_tag(
                        row.find("a", href=self.__match_path), "OneFootball match link"
                    )
                )

    @staticmethod
    def _validate_empty_matches(main: Tag) -> None:
        empty = require_tag(
            main.select_one('section[class*="EmptyState"]'),
            "OneFootball empty matches state",
        )
        require_tag(
            empty.select_one('img[src*="meditation-on-ball"]'),
            "OneFootball empty matches illustration",
        )
        title = required_text(
            require_tag(empty.find("p"), "OneFootball empty matches title"),
            "OneFootball empty matches title",
        )
        if title == "There are no matches available":
            return
        # Localized empty states must belong to the fixtures or results tab.
        require_tag(
            main.select_one(
                'a[class*="linkActive"][href$="/fixtures"], '
                'a[class*="linkActive"][href$="/results"]'
            ),
            "OneFootball empty matches tab",
        )

    @override
    async def _generate_hash(self, item: Item) -> str:
        match_id = urlsplit(item.link).path.rstrip("/").rsplit("/", 1)[-1]
        return HashService.hash_str(match_id)

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)
        return [
            link
            for link in soup.select(f"main {self.__match_lists_selector} a[href]")
            if self.__match_path.fullmatch(str(link["href"]))
        ][:2]

    @override
    async def _get_post_title(self, post: Tag) -> str:
        return self._match_title(post)

    @staticmethod
    def _match_title(post: Tag) -> str:
        team_names = post.select('span[class*="simpleMatchCardTeam__name"]')
        if len(team_names) != 2:
            raise ValueError("Could not find both team names")

        return " vs ".join(
            required_text(team, "OneFootball team name") for team in team_names
        )

    @override
    async def _get_post_datetime(self, post: Tag) -> datetime:
        time_tag = post.find("time")
        datetime_attr = time_tag.get("datetime") if isinstance(time_tag, Tag) else None
        if isinstance(datetime_attr, str) and datetime_attr.strip():
            return parse_datetime(datetime_attr)
        return constant_datetime

    @override
    async def _get_post_link(self, post: Tag) -> str:
        if "href" not in post.attrs:
            raise ValueError("Match tag has no 'href' attribute")
        href = post["href"]
        if not isinstance(href, str):
            raise ValueError(  # noqa: TRY004 - malformed page data is a value error
                "Match 'href' attribute is not a string"
            )
        return urljoin(self.__base_url, href)
