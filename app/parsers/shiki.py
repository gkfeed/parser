from datetime import timedelta, datetime
from typing import override

from bs4.element import Tag

from app.utils.datetime import convert_datetime
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin


class ShikiFeed(PostToItemsMixin, ItemsHashExtension, HttpParserExtension):
    _cache_storage_time = timedelta(hours=1)
    _cache_storage_time_if_success = timedelta(days=1)

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self._url)
        menu_links = soup.find_all(class_="b-menu-links")

        if not menu_links:
            raise ValueError("No elements with class 'b-menu-links' found.")

        menu_link = menu_links[0]
        if not isinstance(menu_link, Tag):
            raise ValueError(
                "The first element with class 'b-menu-links' is not a Tag instance."
            )

        return [
            n
            for n in reversed(list(menu_link.find_all(class_="entry")))
            if isinstance(n, Tag)
        ]

    @override
    async def _get_post_title(self, post: Tag) -> str:
        show_title = await self._show_title
        status = self._get_item_status(post)
        return f"{show_title} {status}"

    @override
    async def _get_post_text(self, post: Tag) -> str:
        return self._get_item_status(post)

    @override
    async def _get_post_link(self, post: Tag) -> str:
        return self._url

    @override
    async def _get_post_datetime(self, post: Tag) -> datetime:
        span_tag = post.find("span")
        if isinstance(span_tag, Tag):
            time_tag = span_tag.find("time")
            if isinstance(time_tag, Tag):
                datetime_str = time_tag.get("datetime")
                if isinstance(datetime_str, str):
                    return convert_datetime(datetime_str)
        return await super()._get_post_datetime(post)

    @property
    async def _show_title(self) -> str:
        soup = await self.get_soup(self._url)
        h1 = soup.find("h1")

        if not isinstance(h1, Tag):
            raise ValueError("h1 tag not found or not a Tag instance.")

        return h1.text

    @property
    def _url(self) -> str:
        return self.feed.url.replace("shikimori.me", "shikimori.one")

    def _get_item_status(self, item: Tag) -> str:
        span_tag = item.find_all("span")[-1]
        if isinstance(span_tag, Tag):
            return span_tag.text
        raise ValueError
