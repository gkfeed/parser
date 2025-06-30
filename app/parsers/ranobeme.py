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
        chapters = [
            ch for ch in soup.find_all(class_="t-b-dotted") if isinstance(ch, Tag)
        ]
        return [ch for ch in chapters if len(ch.find_all("img")) == 1]

    def _get_post_title(self, post: Tag) -> str:
        a_tag = post.find("a")
        if a_tag and isinstance(a_tag, Tag):
            return a_tag.text
        raise ValueError("Could not find post title.")

    async def _get_post_text(self, post: Tag) -> str:
        soup = await self.get_soup(self._get_post_link(post))
        chapter_div = soup.find(class_="chapter")
        if chapter_div and isinstance(chapter_div, Tag):
            paragraphs = [
                p.text for p in chapter_div.find_all("p") if isinstance(p, Tag)
            ]
            return "<br/><br/>".join(paragraphs)
        raise ValueError("Could not find post text.")

    @property
    async def _update_time(self) -> datetime:
        soup = await self.get_soup(self.feed.url)
        uptodate_tag = soup.find(class_="uptodate")
        if (
            uptodate_tag
            and isinstance(uptodate_tag, Tag)
            and "data-time" in uptodate_tag.attrs
        ):
            timestamp_str = uptodate_tag["data-time"]
            if isinstance(timestamp_str, str):
                timestamp = int(timestamp_str)
                tz = timezone(offset=timedelta(hours=0))
                return datetime.fromtimestamp(timestamp, tz)
        raise ValueError("Could not determine update time.")

    def _get_post_link(self, post: Tag) -> str:
        a_tag = post.find("a")
        if a_tag and isinstance(a_tag, Tag) and "href" in a_tag.attrs:
            href = a_tag["href"]
            if isinstance(href, str):
                return self._base_url + href
        raise ValueError("Could not find post link.")
