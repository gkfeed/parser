from typing import override
from bs4 import Tag

from app.extensions.parsers.selenium import SeleniumParserExtension
from app.services.http import HttpService
from app.extensions.parsers.post_to_items import PostToItemsMixin


class RezkaFeed(PostToItemsMixin, SeleniumParserExtension):
    @property
    @override
    async def _posts(self) -> list[Tag]:
        show_url = self.feed.url
        soup = await self._show_soup

        if "/films/" in show_url:
            h2_tags = soup.find_all("h2")
            if not h2_tags:
                raise ValueError("Could not extract h2 tags: No <h2> tags found")
            last_h2 = h2_tags[-1]
            if not isinstance(last_h2, Tag):
                raise ValueError("Last h2 is not a Tag")
            return [last_h2]
        else:
            active_season = soup.select_one(".b-simple_season__item.active")
            tab_id = active_season.get("data-tab_id") if active_season else "1"
            tab_id = str(tab_id) if tab_id else "1"
            return self._extract_episodes(soup, tab_id)

    @override
    async def _get_post_title(self, post: Tag) -> str:
        show_url = self.feed.url
        if "/films/" in show_url:
            return post.text
        else:
            soup = await self._show_soup
            title = self._extract_title(soup)
            active_season = soup.select_one(".b-simple_season__item.active")
            season_text = active_season.text if active_season else "1 Сезон"
            return f"{title} {season_text} {post.text}"

    @override
    async def _get_post_text(self, post: Tag) -> str:
        return post.text

    @override
    async def _get_post_link(self, post: Tag) -> str:
        return self.feed.url

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
