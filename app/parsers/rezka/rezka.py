from bs4 import Tag
from app.serializers.feed import Item
from app.utils.datetime import constant_datetime

from app.extensions.parsers.selenium import SeleniumParserExtension


class RezkaFeed(SeleniumParserExtension):
    @property
    async def items(self) -> list[Item]:
        show_url = self.feed.url
        return [
            Item(
                title=await self._show_status,
                link=show_url,
                text=await self._show_status,
                date=constant_datetime,
            )
        ]

    @property
    async def _show_status(self) -> str:
        soup = await self.get_soup(self.feed.url)
        title = self._extract_title(soup)
        last_season_text = self._extract_last_season_text(soup)
        last_episode_text = self._extract_last_episode_text(soup)

        return f"{title} {last_season_text} {last_episode_text}"

    def _extract_title(self, soup: Tag) -> str:
        title_tag = soup.find("h1")
        if not (title_tag and isinstance(title_tag, Tag)):
            raise ValueError(
                "Could not extract title: <h1> tag not found or not a Tag instance."
            )
        return title_tag.text

    def _extract_last_season_text(self, soup: Tag) -> str:
        seasons = [
            s
            for s in soup.find_all(class_="b-simple_season__item")
            if isinstance(s, Tag)
        ]
        if not (seasons and isinstance(seasons[-1], Tag)):
            raise ValueError(
                "Could not extract last season text: seasons not found or last season not a Tag instance."
            )
        return seasons[-1].text

    def _extract_last_episode_text(self, soup: Tag) -> str:
        a_tags = [
            a
            for a in soup.find_all(class_="b-simple_episode__item")
            if isinstance(a, Tag)
        ]
        if not a_tags:
            raise ValueError("Could not extract last episode text")

        return a_tags[-1].text
