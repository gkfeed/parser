from datetime import datetime

from bs4 import Tag

from app.utils.datetime import convert_datetime, constant_datetime
from app.serializers.feed import Item
from app.extensions.parsers.http import HttpParserExtension


class XFeed(HttpParserExtension):
    _base_url = "https://nitter.esmailelbob.xyz/"
    _x_url = "https://x.com"

    @property
    async def items(self) -> list[Item]:
        return [
            Item(
                title=self._get_post_title(p),
                text=self._get_post_text(p),
                date=self._get_post_datetime(p),
                link=self._get_post_link(p),
            )
            for p in await self._posts
        ]

    @property
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed_url)
        posts = [p for p in soup.find_all(class_="timeline-item") if isinstance(p, Tag)]
        return posts

    def _get_post_title(self, post: Tag) -> str:
        media_body = post.find(class_="media-body")
        if media_body and isinstance(media_body, Tag):
            return media_body.text.strip()
        raise ValueError

    def _get_post_text(self, post: Tag) -> str:
        return self._get_post_title(post)

    def _get_post_link(self, post: Tag) -> str:
        link_tag = post.find("a")
        if link_tag and isinstance(link_tag, Tag) and "href" in link_tag.attrs:
            return self._x_url + str(link_tag["href"])
        raise ValueError

    def _get_post_datetime(self, post: Tag) -> datetime:
        date_tag = post.find(class_="tweet-date")
        if date_tag and isinstance(date_tag, Tag):
            date_str = date_tag.a.text if date_tag.a else ""
            if date_str:
                return convert_datetime(date_str)
        return constant_datetime

    @property
    def feed_url(self) -> str:
        href = self.feed.url.split("/")[-1]
        if self.feed.url.endswith("/"):
            href = self.feed.url.split("/")[-2]
        return self._base_url + href
