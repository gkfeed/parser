from datetime import timedelta

from bs4 import Tag

from app.serializers.feed import Item
from app.utils.datetime import constant_datetime
from app.extentions.parsers.selenium import SeleniumParserExtention
from app.extentions.parsers.cache import CacheFeedExtention


class MangaLibFeed(SeleniumParserExtention, CacheFeedExtention):
    _cache_storage_time = timedelta(hours=1)
    _selenium_wait_time = 5
    _base_url = "https://mangalib.org"
    _max_posts = 5

    @property
    async def items(self) -> list[Item]:
        return [
            Item(
                title=self._get_post_title(p),
                text=self._get_post_text(p),
                date=constant_datetime,
                link=self._get_post_link(p),
            )
            for p in await self._posts
        ]

    @property
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url + "?section=chapters")
        posts = [p for p in soup.find_all(class_="acu_az")][: self._max_posts]
        return posts

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
