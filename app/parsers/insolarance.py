from datetime import timedelta
from typing import override

from bs4 import Tag

from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin


class InsolaranceFeed(PostToItemsMixin, HttpParserExtension, CacheFeedExtension):
    _cache_storage_time_if_success = timedelta(hours=1)

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)
        return [p for p in soup.find_all("article") if isinstance(p, Tag)]

    @override
    async def _get_post_title(self, post: Tag) -> str:
        a_tags = post.find_all("a")
        if len(a_tags) >= 2 and isinstance(a_tags[-2], Tag):
            return a_tags[-2].text.strip()
        raise ValueError("Could not extract post title")

    @override
    async def _get_post_link(self, post: Tag) -> str:
        a_tags = post.find_all("a")
        if len(a_tags) >= 2:
            tag = a_tags[-2]
            if isinstance(tag, Tag):
                href = tag.get("href")
                if isinstance(href, str):
                    return href
        raise ValueError("Could not extract post link")
