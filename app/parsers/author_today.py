from datetime import datetime, timedelta
from typing import override
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemIdentityHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.utils.html import require_tag, required_attr, required_text


class AuthorTodayFeed(
    PostToItemsMixin, ItemIdentityHashExtension, HttpParserExtension, CacheFeedExtension
):
    empty_result_delay = timedelta(hours=1)
    _base_url = "https://author.today"

    @override
    def _validate_html(self, url: str, html: bytes) -> None:
        soup = BeautifulSoup(html, "html.parser")
        # An empty chapter list is valid; a missing list is not.
        require_tag(
            soup.select_one("#tab-chapters ul.table-of-content"),
            "Author.Today table of contents",
        )

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)
        return [
            chapter
            for chapter in soup.select("#tab-chapters .table-of-content > li")
            if isinstance(chapter, Tag)
        ]

    def _get_chapter_anchor(self, post: Tag) -> Tag:
        return require_tag(
            post.select_one("a[href^='/reader/']"), "Author.Today chapter link"
        )

    @override
    async def _get_post_title(self, post: Tag) -> str:
        chapter_link = self._get_chapter_anchor(post)
        return required_text(chapter_link, "Author.Today chapter title", separator=" ")

    @override
    async def _get_post_link(self, post: Tag) -> str:
        chapter_link = self._get_chapter_anchor(post)
        href = required_attr(chapter_link, "href", "Author.Today chapter link")
        return urljoin(self._base_url, href)

    @override
    async def _get_post_datetime(self, post: Tag) -> datetime:
        field = "Author.Today chapter publication time"
        published_at = require_tag(
            post.select_one(".chapter-publish-time [data-time]"), field
        )
        value = required_attr(published_at, "data-time", field)
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"Invalid {field}: {value!r}") from exc
