from datetime import timedelta

from bs4 import Tag

from app.utils.datetime import constant_datetime
from app.serializers.feed import Item
from app.extentions.parsers.http import HttpParserExtention
from app.extentions.parsers.cache import CacheFeedExtention


class InsolaranceFeed(HttpParserExtention, CacheFeedExtention):
    _cache_storage_time_if_success = timedelta(hours=1)

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
        soup = await self.get_soup(self.feed.url)
        return [p for p in soup.find_all("article")]

    def _get_post_title(self, post: Tag) -> str:
        try:
            return post.find_all("a")[-2].text.strip()
        except IndexError:
            raise ValueError

    def _get_post_text(self, post: Tag) -> str:
        return self._get_post_title(post)

    def _get_post_link(self, post: Tag) -> str:
        try:
            return post.find_all("a")[-2]["href"]
        except IndexError:
            raise ValueError
