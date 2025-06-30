from datetime import timedelta

from bs4 import Tag

from app.utils.datetime import constant_datetime
from app.serializers.feed import Item
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.cache import CacheFeedExtension


class InsolaranceFeed(HttpParserExtension, CacheFeedExtension):
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
        return [p for p in soup.find_all("article") if isinstance(p, Tag)]

    def _get_post_title(self, post: Tag) -> str:
        a_tags = post.find_all("a")
        if len(a_tags) >= 2 and isinstance(a_tags[-2], Tag):
            return a_tags[-2].text.strip()
        raise ValueError("Could not extract post title")

    def _get_post_text(self, post: Tag) -> str:
        return self._get_post_title(post)

    def _get_post_link(self, post: Tag) -> str:
        a_tags = post.find_all("a")
        if (
            len(a_tags) >= 2
            and isinstance(a_tags[-2], Tag)
            and "href" in a_tags[-2].attrs
        ):
            href = a_tags[-2]["href"]
            if isinstance(href, str):
                return href
        raise ValueError("Could not extract post link")
