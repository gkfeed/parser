from typing import override
from bs4 import Tag

from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin


class YummyAnimeFeed(PostToItemsMixin, HttpParserExtension):
    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self._show_url)
        return [soup]

    @override
    async def _get_post_title(self, post: Tag) -> str:
        title = await self._show_title(post)
        status = await self._show_status(post)
        return f"{title} {status}"

    @override
    async def _get_post_text(self, post: Tag) -> str:
        return await self._show_status(post)

    @override
    async def _get_post_link(self, post: Tag) -> str:
        return self._show_url

    async def _show_status(self, soup: Tag) -> str:
        try:
            return soup.find_all(class_="anime-r")[1].text
        except IndexError:
            raise ValueError

    async def _show_title(self, soup: Tag) -> str:
        try:
            return soup.find_all("h1")[0].text
        except IndexError:
            raise ValueError("Couldn'n find status of show: " + self._show_url)

    @property
    def _show_url(self) -> str:
        return self.feed.url.replace("yummyanime", "yummy-anime")
