from datetime import timedelta
from typing import override

from bs4 import Tag

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemIdentityHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.utils.html import require_tag, required_attr


class InsolaranceFeed(
    PostToItemsMixin, ItemIdentityHashExtension, HttpParserExtension, CacheFeedExtension
):
    _cache_storage_time_if_success = timedelta(hours=1)

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)
        return [p for p in soup.find_all("article") if isinstance(p, Tag)]

    @override
    async def _get_post_title(self, post: Tag) -> str:
        a_tags = post.find_all("a")
        title = require_tag(
            a_tags[-2] if len(a_tags) >= 2 else None, "Insolarance post title"
        )
        return title.text.strip()

    @override
    async def _get_post_link(self, post: Tag) -> str:
        a_tags = post.find_all("a")
        link = require_tag(
            a_tags[-2] if len(a_tags) >= 2 else None, "Insolarance post link"
        )
        return required_attr(link, "href", "Insolarance post link")
