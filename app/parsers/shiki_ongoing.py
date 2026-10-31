from datetime import datetime, timedelta
from typing import override

from bs4 import BeautifulSoup, Tag

from app.extensions.parsers.exceptions import FeedUnavailable
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.utils.datetime import constant_datetime
from app.utils.html import require_tag, required_attr, required_text


class ShikiOngoingFeed(PostToItemsMixin, ItemsHashExtension, HttpParserExtension):
    empty_result_delay = timedelta(hours=1)
    success_result_delay = timedelta(days=1)

    @override
    def _validate_html(self, url: str, html: bytes) -> None:
        self._get_ongoings_container(BeautifulSoup(html, "html.parser"))

    def _get_ongoings_container(self, soup: BeautifulSoup) -> Tag:
        container = soup.find("div", class_="fc-ongoings")
        if not isinstance(container, Tag):
            raise FeedUnavailable(self.feed.url, "missing_ongoings_container")
        return container

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)

        container = self._get_ongoings_container(soup)

        return [a for a in container.find_all("article") if isinstance(a, Tag)]

    @override
    async def _get_post_title(self, post: Tag) -> str:
        title_tag = require_tag(
            post.find("span", class_="name-en"), "Shiki ongoing title"
        )
        return required_text(title_tag, "Shiki ongoing title")

    @override
    async def _get_post_link(self, post: Tag) -> str:
        link_tag = require_tag(post.find("a"), "Shiki ongoing link")
        return required_attr(link_tag, "href", "Shiki ongoing link")

    @override
    async def _get_post_datetime(self, post: Tag) -> datetime:
        date_meta = post.find("meta", itemprop="dateCreated")
        if isinstance(date_meta, Tag):
            date_content = date_meta.get("content")
            if isinstance(date_content, str) and date_content:
                return datetime.fromisoformat(date_content)
        return constant_datetime
