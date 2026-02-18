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
            h2_tags = soup.find_all("h2")
            if not h2_tags:
                raise ValueError("Could not extract h2 tags: No <h2> tags found")

            h2_tag = h2_tags[-1]

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
            return await self._extract_last_season_episodes_items(soup, title)

        return items

    async def _extract_last_season_episodes_items(
        self, soup: Tag, title: str
    ) -> list[Item]:
        active_season = soup.select_one(".b-simple_season__item.active")

        if active_season:
            season_text = active_season.text
            tab_id = active_season.get("data-tab_id")
            tab_id = str(tab_id) if tab_id else "1"
        else:
            # FIXME: do not hardcode number to 1 get actual last
            season_text = "1 Сезон"
            tab_id = "1"

        episodes = self._extract_episodes(soup, tab_id)
        return [
            Item(
                title=f"{title} {season_text} {ep.text}",
                link=self.feed.url,
                text=ep.text,
                date=constant_datetime,
            )
            for ep in episodes
        ]

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

    def _extract_episodes(self, soup: Tag, tab_id: str) -> list[Tag]:
        container = soup.find(id=f"simple-episodes-list-{tab_id}")
        if not container or not isinstance(container, Tag):
            raise ValueError(
                f"Could not extract episodes container for tab_id {tab_id}"
            )

        return [
            a
            for a in container.find_all(class_="b-simple_episode__item")
            if isinstance(a, Tag)
        ]
