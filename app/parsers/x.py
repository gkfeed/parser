from datetime import datetime

from bs4 import Tag

from app.utils.datetime import convert_datetime, constant_datetime
from app.serializers.feed import Item
from app.extentions.parsers.http import HttpParserExtention


class XFeed(HttpParserExtention):
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
        posts = [p for p in soup.find_all(class_="timeline-item")]
        return posts

    def _get_post_title(self, post: Tag) -> str:
        try:
            return post.find_all(class_="media-body")[0].text.strip()
        except IndexError:
            raise ValueError

    def _get_post_text(self, post: Tag) -> str:
        return self._get_post_title(post)

    def _get_post_link(self, post: Tag) -> str:
        try:
            return self._x_url + post.find_all("a")[0]["href"]
        except IndexError:
            raise ValueError

    def _get_post_datetime(self, post: Tag) -> datetime:
        return constant_datetime
        try:
            date_str = post.find_all(class_="tweet-date")[0].a.text
            return convert_datetime(date_str)
        except IndexError:
            raise ValueError

    @property
    def feed_url(self) -> str:
        href = self.feed.url.split("/")[-1]
        if self.feed.url.endswith("/"):
            href = self.feed.url.split("/")[-2]
        return self._base_url + href
