from bs4 import Tag

from app.utils.datetime import constant_datetime
from app.serializers.feed import Item
from app.extensions.parsers.http import HttpParserExtension


class PornHubFeed(HttpParserExtension):
    _base_url = "https://www.pornhub.com"

    @property
    async def items(self) -> list[Item]:
        return [
            Item(
                title=self._get_video_title(p),
                text=self._get_video_title(p),
                date=constant_datetime,
                link=self._get_video_link(p),
            )
            for p in await self._posts
        ]

    @property
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)
        posts = [
            p for p in soup.find_all("a", class_="linkVideoThumb") if isinstance(p, Tag)
        ]
        return posts

    def _get_video_title(self, post: Tag) -> str:
        if post.img and "title" in post.img.attrs:
            return post.img["title"]
        raise ValueError("No title found in post")

    def _get_video_link(self, post: Tag) -> str:
        if "href" in post.attrs:
            return self._base_url + post["href"]
        raise ValueError("No link found in post")
