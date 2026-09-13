from datetime import datetime, timedelta
from typing import override
from urllib.parse import urljoin

from bs4 import Tag

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin


class AuthorTodayFeed(PostToItemsMixin, HttpParserExtension, CacheFeedExtension):
    _cache_storage_time = timedelta(hours=1)
    _base_url = "https://author.today"

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)
        return [
            chapter
            for chapter in soup.select("#tab-chapters .table-of-content > li")
            if isinstance(chapter, Tag)
        ]

    @override
    async def _get_post_title(self, post: Tag) -> str:
        chapter_link = post.select_one("a[href^='/reader/']")
        if isinstance(chapter_link, Tag):
            title = chapter_link.get_text(" ", strip=True)
            if title:
                return title
        raise ValueError("Could not find chapter title")

    @override
    async def _get_post_link(self, post: Tag) -> str:
        chapter_link = post.select_one("a[href^='/reader/']")
        href = chapter_link.get("href") if isinstance(chapter_link, Tag) else None
        if isinstance(href, str):
            return urljoin(self._base_url, href)
        raise ValueError("Could not find chapter link")

    @override
    async def _get_post_datetime(self, post: Tag) -> datetime:
        published_at = post.select_one(".chapter-publish-time [data-time]")
        value = published_at.get("data-time") if published_at else None
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        raise ValueError("Could not find chapter publication time")
