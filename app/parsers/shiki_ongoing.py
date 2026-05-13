from datetime import datetime, timedelta
from typing import override

from bs4 import Tag

from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin

from app.utils.datetime import constant_datetime


class ShikiOngoingFeed(PostToItemsMixin, ItemsHashExtension, HttpParserExtension):
    _cache_storage_time = timedelta(hours=1)
    _cache_storage_time_if_success = timedelta(days=1)

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)

        container = soup.find("div", class_="fc-ongoings")
        if not isinstance(container, Tag):
            return []

        return [a for a in container.find_all("article") if isinstance(a, Tag)]

    @override
    async def _get_post_title(self, post: Tag) -> str:
        title_tag = post.find("span", class_="name-en")
        if title_tag and isinstance(title_tag, Tag):
            return title_tag.text
        raise ValueError("Title not found")

    @override
    async def _get_post_link(self, post: Tag) -> str:
        link_tag = post.find("a")
        if link_tag and isinstance(link_tag, Tag):
            href = link_tag.get("href")
            if isinstance(href, str):
                return href
        raise ValueError("Link not found")

    @override
    async def _get_post_datetime(self, post: Tag) -> datetime:
        date_meta = post.find("meta", itemprop="dateCreated")
        if (
            date_meta
            and isinstance(date_meta, Tag)
            and (date_content := date_meta.get("content"))
            and isinstance(date_content, str)
        ):
            return datetime.fromisoformat(date_content)
        return constant_datetime
