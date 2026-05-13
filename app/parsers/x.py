from datetime import datetime
from typing import override

from bs4 import Tag

from app.utils.datetime import convert_datetime
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin


class XFeed(PostToItemsMixin, HttpParserExtension):
    _base_url = "https://nitter.esmailelbob.xyz/"
    _x_url = "https://x.com"

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed_url)
        return [p for p in soup.find_all(class_="timeline-item") if isinstance(p, Tag)]

    @override
    async def _get_post_title(self, post: Tag) -> str:
        media_body = post.find(class_="media-body")
        if media_body and isinstance(media_body, Tag):
            return media_body.text.strip()
        raise ValueError

    @override
    async def _get_post_link(self, post: Tag) -> str:
        link_tag = post.find("a")
        if link_tag and isinstance(link_tag, Tag) and "href" in link_tag.attrs:
            return self._x_url + str(link_tag["href"])
        raise ValueError

    @override
    async def _get_post_datetime(self, post: Tag) -> datetime:
        date_tag = post.find(class_="tweet-date")
        if date_tag and isinstance(date_tag, Tag):
            date_str = date_tag.a.text if date_tag.a else ""
            if date_str:
                return convert_datetime(date_str)
        return await super()._get_post_datetime(post)

    @property
    def feed_url(self) -> str:
        href = self.feed.url.split("/")[-1]
        if self.feed.url.endswith("/"):
            href = self.feed.url.split("/")[-2]
        return self._base_url + href
