from datetime import datetime, timedelta, timezone
from typing import override

from bs4 import Tag

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin


class RanobeMeFeed(PostToItemsMixin, HttpParserExtension, CacheFeedExtension):
    _base_url = "https://ranobe.me"
    _cache_storage_time = timedelta(hours=1)

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self._base_url + "/news")
        feed_path = self.feed.url.removeprefix(self._base_url).rstrip("/")
        chapters: dict[str, Tag] = {}

        for title_link in soup.select(f'.FicTable_Title a[href="{feed_path}"]'):
            chapter_list = title_link.find_next("div", class_="news_chapters_list")
            if not isinstance(chapter_list, Tag):
                continue
            for chapter_link in chapter_list.select("a[href]"):
                href = chapter_link.get("href")
                if isinstance(href, str):
                    chapters[href] = chapter_link

        return list(chapters.values())

    @override
    async def _get_post_title(self, post: Tag) -> str:
        if title := post.get_text(strip=True):
            return title
        raise ValueError("Could not find post title.")

    @override
    async def _get_post_text(self, post: Tag) -> str:
        soup = await self.get_soup(await self._get_post_link(post))
        chapter_div = soup.find(class_="chapter")
        if chapter_div and isinstance(chapter_div, Tag):
            paragraphs = [
                p.text for p in chapter_div.find_all("p") if isinstance(p, Tag)
            ]
            return "<br/><br/>".join(paragraphs)
        raise ValueError("Could not find post text.")

    @override
    async def _get_post_link(self, post: Tag) -> str:
        href = post.get("href")
        if isinstance(href, str):
            return self._base_url + href
        raise ValueError("Could not find post link.")

    @override
    async def _get_post_datetime(self, post: Tag) -> datetime:
        chapter_list = post.find_parent("div", class_="news_chapters_list")
        news_date = (
            chapter_list.find_next_sibling("div", class_="news_date")
            if isinstance(chapter_list, Tag)
            else None
        )
        uptodate_tag = (
            news_date.find(class_="uptodate") if isinstance(news_date, Tag) else None
        )
        if isinstance(uptodate_tag, Tag):
            timestamp_str = uptodate_tag.get("data-time")
            if isinstance(timestamp_str, str):
                timestamp = int(timestamp_str)
                tz = timezone(offset=timedelta(hours=0))
                return datetime.fromtimestamp(timestamp, tz)
        raise ValueError("Could not determine update time.")
