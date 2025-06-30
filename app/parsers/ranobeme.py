from datetime import timedelta, datetime, timezone

from bs4 import Tag

from app.serializers.feed import Item
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.cache import CacheFeedExtension


class RanobeMeFeed(HttpParserExtension, CacheFeedExtension):
    _base_url = "https://ranobe.me"
    _cache_storage_time = timedelta(hours=1)

    @property
    async def items(self) -> list[Item]:
        return [
            Item(
                title=self._get_post_title(p),
                text=await self._get_post_text(p),
                date=await self._update_time,
                link=self._get_post_link(p),
            )
            for p in await self._posts
        ]

    @property
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)
        chapters = soup.find_all(class_="t-b-dotted")
        return [ch for ch in chapters if len(ch.find_all("img")) == 1]

    def _get_post_title(self, post: Tag) -> str:
        try:
            return post.find_all("a")[0].text
        except IndexError:
            raise ValueError

    async def _get_post_text(self, post: Tag) -> str:
        try:
            soup = await self.get_soup(self._get_post_link(post))
            paragraphs = soup.find_all(class_="chapter")[0].find_all("p")
            return "<br/><br/>".join(p.text for p in paragraphs)
        except IndexError:
            raise ValueError

    @property
    async def _update_time(self) -> datetime:
        try:
            soup = await self.get_soup(self.feed.url)
            timestamp = int(soup.find_all(class_="uptodate")[0]["data-time"])
            tz = timezone(offset=timedelta(hours=0))
            return datetime.fromtimestamp(timestamp, tz)
        except IndexError:
            raise ValueError

    def _get_post_link(self, post: Tag) -> str:
        try:
            return self._base_url + str(post.a["href"])
        except IndexError:
            raise ValueError
