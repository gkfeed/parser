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
        chapter_tags = soup.find_all(attrs={"data-chapter-id": True})
        return chapter_tags[: self._max_posts]

    def _get_post_title(self, post: Tag) -> str:
        try:
            return post.find_all("a")[0].text.strip()
        except IndexError:
            raise ValueError

    def _get_post_text(self, post: Tag) -> str:
        return self._get_post_title(post)

    def _get_post_link(self, post: Tag) -> str:
        try:
            return self._base_url + post.find_all("a")[0]["href"]
        except IndexError:
            raise ValueError
