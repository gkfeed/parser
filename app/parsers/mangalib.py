from datetime import timedelta
from typing import override

from bs4 import Tag

from app.extensions.parsers.selenium import SeleniumParserExtension
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin


class MangaLibFeed(PostToItemsMixin, SeleniumParserExtension, CacheFeedExtension):
    _cache_storage_time = timedelta(hours=1)
    _selenium_wait_time = 5
    _base_url = "https://mangalib.org"
    _max_posts = 5

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url + "?section=chapters")
        chapter_tags = [
            tag
            for tag in soup.find_all(attrs={"data-chapter-id": True})
            if isinstance(tag, Tag)
        ]
        return chapter_tags[: self._max_posts]

    @override
    async def _get_post_title(self, post: Tag) -> str:
        a_tag = post.find("a")
        if a_tag and isinstance(a_tag, Tag):
            return a_tag.text.strip()
        raise ValueError("Could not extract post title")

    @override
    async def _get_post_link(self, post: Tag) -> str:
        a_tag = post.find("a")
        if a_tag and isinstance(a_tag, Tag) and "href" in a_tag.attrs:
            href = a_tag["href"]
            if isinstance(href, str):
                return self._base_url + href
        raise ValueError("Could not extract post link")
