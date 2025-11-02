from bs4 import Tag, BeautifulSoup
from datetime import datetime

from app.extensions.parsers.http import HttpParserExtension
from app.serializers.feed import Item


class LiquidpediaFeed(HttpParserExtension):
    @property
    async def items(self) -> list[Item]:
        soup = await self.get_soup(self.feed.url)
        items = []

        matches_element = await self._extract_matches_element(soup)
        matches = matches_element.find_all("table")
        if not matches:
            raise ValueError("Could not find any match tables.")

        for match in matches:
            if not isinstance(match, Tag):
                raise ValueError("Match element is not Tag")
            item = await self._parse_match(match)
            items.append(item)

        return items

    async def _extract_matches_element(self, soup: BeautifulSoup) -> Tag:
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

    async def _extract_datetime_from_match(self, match_tag: Tag) -> datetime:
        timer_span = match_tag.find(
            "span", class_="timer-object timer-object-countdown-only"
        )
        if not isinstance(timer_span, Tag):
            raise ValueError("Timer span not found or not a Tag.")

        timestamp_str = timer_span.get("data-timestamp")
        if not isinstance(timestamp_str, str):
            raise ValueError("data-timestamp attribute not found or not a string.")

        try:
            timestamp = int(timestamp_str)
            match_datetime = datetime.fromtimestamp(timestamp)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid timestamp: {timestamp_str}")

        return match_datetime

    async def _parse_match(self, match: Tag) -> Item:
        team_left_tag = match.find(class_="team-left")
        if not isinstance(team_left_tag, Tag):
            raise ValueError("Team left tag not found or not a Tag.")

        team_right_tag = match.find(class_="team-right")
        if not isinstance(team_right_tag, Tag):
            raise ValueError("Team right tag not found or not a Tag.")

        team_left_img = team_left_tag.find("img")
        if not isinstance(team_left_img, Tag):
            raise ValueError("Team left image not found or not a Tag.")

        team_right_img = team_right_tag.find("img")
        if not isinstance(team_right_img, Tag):
            raise ValueError("Team right image not found or not a Tag.")

        team_left = team_left_img.get("alt")
        team_right = team_right_img.get("alt")

        if not isinstance(team_left, str) or not isinstance(team_right, str):
            raise ValueError("Team names not found or not strings.")

        match_datetime = await self._extract_datetime_from_match(match)

        return Item(
            title=f"{team_left} vs {team_right}",
            text="",
            link=self.feed.url,
            date=match_datetime,
        )
