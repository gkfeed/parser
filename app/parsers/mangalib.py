from datetime import timedelta

from bs4 import Tag

from app.serializers.feed import Item
from app.utils.datetime import constant_datetime
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.extensions.parsers.cache import CacheFeedExtension


class MangaLibFeed(SeleniumParserExtension, CacheFeedExtension):
    _cache_storage_time = timedelta(hours=1)
    _selenium_wait_time = 5
    _base_url = "https://mangalib.org"
    _max_posts = 5

    @property
    async def items(self) -> list[Item]:
        return [
            Item(
                title=self._get_post_title(c),
                text=self._get_post_text(c),
                date=constant_datetime,
                link=self._get_post_link(c),
            )
            for c in await self._chapters
        ]

    @property
    async def _chapters(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url + "?section=chapters")
        chapter_tags = [
            tag
            for tag in soup.find_all(attrs={"data-chapter-id": True})
            if isinstance(tag, Tag)
        ]
        return chapter_tags[: self._max_posts]

    def _get_post_title(self, post: Tag) -> str:
        a_tag = post.find("a")
        if a_tag and isinstance(a_tag, Tag):
            return a_tag.text.strip()
        raise ValueError("Could not extract post title")

    def _get_post_text(self, post: Tag) -> str:
        return self._get_post_title(post)

    def _get_post_link(self, post: Tag) -> str:
        a_tag = post.find("a")
        if a_tag and isinstance(a_tag, Tag) and "href" in a_tag.attrs:
            href = a_tag["href"]
            if isinstance(href, str):
                return self._base_url + href
        raise ValueError("Could not extract post link")
