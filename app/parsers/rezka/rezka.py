from bs4 import Tag

from app.serializers.feed import Item
from app.utils.datetime import constant_datetime
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.services.http import HttpService


class RezkaFeed(SeleniumParserExtension):
    @property
    async def items(self) -> list[Item]:
        show_url = self.feed.url
        soup = await self._show_soup
        items = []

        if "/films/" in show_url:
            h2_tag = soup.find_all("h2")[-1]

            if not (h2_tag and isinstance(h2_tag, Tag)):
                raise ValueError("Could not extract h2 tag for film")

            items.append(
                Item(
                    title=h2_tag.text,
                    link=show_url,
                    text=h2_tag.text,
                    date=constant_datetime,
                )
            )
        else:
            title = self._extract_title(soup)
            season = self._extract_active_season(soup)
            episodes = self._extract_episodes(soup, season)
            [
                items.append(
                    Item(
                        title=f"{title} {season.text} {ep.text}",
                        link=show_url,
                        text=ep.text,
                        date=constant_datetime,
                    )
                )
                for ep in episodes
            ]

        return items

    @property
    async def _show_soup(self) -> Tag:
        _url = self.feed.url

        status = await HttpService.get_status(_url)
        if status != 200 and not _url.endswith("-latest.html"):
            _url = _url.replace(".html", "-latest.html")

        return await self.get_soup(_url)

    def _extract_title(self, soup: Tag) -> str:
        title_tag = soup.find("h1")
        if not (title_tag and isinstance(title_tag, Tag)):
            raise ValueError(
                "Could not extract title: <h1> tag not found or not a Tag instance."
            )
        return title_tag.text

    def _extract_active_season(self, soup: Tag) -> Tag:
        active_season = soup.find(class_="b-simple_season__item active")

        if not active_season or not isinstance(active_season, Tag):
            raise ValueError("Could not extract active season")

        return active_season

    def _extract_episodes(self, soup: Tag, season: Tag) -> list[Tag]:
        tab_id = season.get("data-tab_id")
        if not tab_id:
            raise ValueError("Could not extract tab_id from active season")

        container = soup.find(id=f"simple-episodes-list-{tab_id}")
        if not container or not isinstance(container, Tag):
            raise ValueError("Could not extract episodes container")

        return [
            a
            for a in container.find_all(class_="b-simple_episode__item")
            if isinstance(a, Tag)
        ]
