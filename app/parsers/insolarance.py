from datetime import timedelta
from typing import override

from bs4 import BeautifulSoup, Tag

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemIdentityHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.utils.html import require_tag, required_attr, required_text


class InsolaranceFeed(
    PostToItemsMixin, ItemIdentityHashExtension, HttpParserExtension, CacheFeedExtension
):
    _cache_storage_time_if_success = timedelta(hours=1)

    @override
    def _validate_html(self, url: str, html: bytes) -> None:
        soup = BeautifulSoup(html, "html.parser")
        posts = require_tag(
            soup.select_one("main#cb-main.cb-posts-loop"), "Insolarance posts loop"
        )
        if posts.find("article") is not None:
            return
        empty = posts.select_one("section.entry-content p")
        if empty and empty.get_text(" ", strip=True).startswith(
            "Sorry, but nothing matched your search terms."
        ):
            return
        raise ValueError("Missing Insolarance posts or empty search result")

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
        return required_text(title, "Insolarance post title")

    @override
    async def _get_post_link(self, post: Tag) -> str:
        a_tags = post.find_all("a")
        link = require_tag(
            a_tags[-2] if len(a_tags) >= 2 else None, "Insolarance post link"
        )
        return required_attr(link, "href", "Insolarance post link")
