from datetime import datetime
from typing import override

from bs4 import Tag

from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin


class LiquidpediaFeed(PostToItemsMixin, ItemsHashExtension, HttpParserExtension, CacheFeedExtension):
    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)
        matches_element = await self._extract_matches_element(soup)
        return [t for t in matches_element.find_all("table") if isinstance(t, Tag)]

    @override
    async def _get_post_title(self, post: Tag) -> str:
        team_left_tag = post.find(class_="team-left")
        team_right_tag = post.find(class_="team-right")

        if not isinstance(team_left_tag, Tag) or not isinstance(team_right_tag, Tag):
            raise ValueError("Team tags not found")

        team_left_img = team_left_tag.find("img")
        team_right_img = team_right_tag.find("img")

        if not isinstance(team_left_img, Tag) or not isinstance(team_right_img, Tag):
            raise ValueError("Team images not found")

        team_left = team_left_img.get("alt")
        team_right = team_right_img.get("alt")

        if not isinstance(team_left, str) or not isinstance(team_right, str):
            raise ValueError("Team names not found")

        return f"{team_left} vs {team_right}"

    @override
    async def _get_post_link(self, post: Tag) -> str:
        return self.feed.url

    @override
    async def _get_post_datetime(self, post: Tag) -> datetime:
        timer_span = post.find("span", class_="timer-object timer-object-countdown-only")
        if not isinstance(timer_span, Tag):
            raise ValueError("Timer span not found")

        timestamp_str = timer_span.get("data-timestamp")
        if not isinstance(timestamp_str, str):
            raise ValueError("data-timestamp not found")

        return datetime.fromtimestamp(int(timestamp_str))

    async def _extract_matches_element(self, soup: Tag) -> Tag:
        infobox_headers = soup.find_all(class_="infobox-header")
        if len(infobox_headers) < 2:
            raise ValueError("Could not find enough infobox headers.")

        infobox_header = infobox_headers[-2]
        if not isinstance(infobox_header, Tag):
            raise ValueError("Infobox header is not a Tag.")

        parent = infobox_header.parent
        if not isinstance(parent, Tag):
            raise ValueError("Infobox header parent is not a Tag.")

        parent_of_parent = parent.parent
        if not isinstance(parent_of_parent, Tag):
            raise ValueError("Infobox header grandparent is not a Tag.")

        return parent_of_parent
