from functools import cached_property
from typing import override

from bs4 import Tag

from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.services.rezka import RezkaClient, RezkaPage, RezkaPageMode


class RezkaFeed(PostToItemsMixin, ItemsHashExtension, SeleniumParserExtension):
    _selenium_wait_time = 5
    _show_page: RezkaPage | None = None

    @cached_property
    def _client(self) -> RezkaClient:
        return RezkaClient(super().get_html)

    @override
    async def get_html(self, url: str, *, attempts: int = 3) -> bytes:
        return await self._client.get_html(url, attempts=attempts)

    @override
    def _validate_html(self, url: str, html: bytes) -> None:
        RezkaClient.validate_html(url, html, self._page_mode)

    @cached_property
    def _page_mode(self) -> RezkaPageMode:
        if "/films/" in self.feed.url:
            return RezkaPageMode.FILM
        return RezkaPageMode.SERIES

    async def _resolve_page(self) -> RezkaPage:
        if self._show_page is None:
            self._show_page = await self._client.resolve(self.feed.url, self._page_mode)
        return self._show_page

    @property
    @override
    async def _posts(self) -> list[Tag]:
        return (await self._resolve_page()).posts

    @override
    async def _get_post_title(self, post: Tag) -> str:
        if self._page_mode is RezkaPageMode.FILM:
            return post.get_text().strip()
        page = await self._resolve_page()
        return f"{page.title} {page.season} {post.get_text().strip()}"

    @override
    async def _get_post_text(self, post: Tag) -> str:
        return post.get_text().strip()

    @override
    async def _get_post_link(self, post: Tag) -> str:
        return (await self._resolve_page()).url
