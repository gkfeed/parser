from datetime import datetime, timedelta
from typing import override
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup
from bs4.element import Tag

from app.core.worker_kind import WorkerKind
from app.extensions.parsers.exceptions import FeedUnavailable
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.utils.datetime import parse_datetime
from app.utils.html import require_tag, required_text


class ShikiFeed(PostToItemsMixin, ItemsHashExtension, HttpParserExtension):
    worker_kind = WorkerKind.LIGHT
    _cache_storage_time = timedelta(hours=1)
    _cache_storage_time_if_success = timedelta(days=1)

    @override
    def _validate_html(self, url: str, html: bytes) -> None:
        soup = BeautifulSoup(html, "html.parser")
        if soup.select_one("#cf-error-details") is not None:
            raise FeedUnavailable(self.feed.url, "cloudflare_error")
        if soup.select_one("#challenge-form, #challenge-running") is not None:
            raise FeedUnavailable(self.feed.url, "cloudflare_challenge")
        required_text(require_tag(soup.find("h1"), "Shiki title"), "Shiki title")
        require_tag(soup.find(class_="b-menu-links"), "Shiki episode history")

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self._url)
        menu_links = soup.find_all(class_="b-menu-links")

        if not menu_links:
            raise ValueError("No elements with class 'b-menu-links' found.")

        menu_link = menu_links[0]
        if not isinstance(menu_link, Tag):
            raise ValueError(  # noqa: TRY004 - missing page data is a value error
                "The first element with class 'b-menu-links' is not a Tag instance."
            )

        return [
            n
            for n in reversed(menu_link.find_all(class_="entry"))
            if isinstance(n, Tag)
        ]

    @override
    async def _get_post_title(self, post: Tag) -> str:
        show_title = await self._show_title
        status = self._get_item_status(post)
        return f"{show_title} {status}"

    @override
    async def _get_post_text(self, post: Tag) -> str:
        return self._get_item_status(post)

    @override
    async def _get_post_link(self, post: Tag) -> str:
        return self._url

    @override
    async def _get_post_datetime(self, post: Tag) -> datetime:
        span_tag = post.find("span")
        time_tag = span_tag.find("time") if isinstance(span_tag, Tag) else None
        datetime_str = time_tag.get("datetime") if isinstance(time_tag, Tag) else None
        if isinstance(datetime_str, str) and datetime_str.strip():
            return parse_datetime(datetime_str)
        return await super()._get_post_datetime(post)

    @property
    async def _show_title(self) -> str:
        soup = await self.get_soup(self._url)
        h1 = soup.find("h1")

        if not isinstance(h1, Tag):
            raise ValueError(  # noqa: TRY004 - missing page data is a value error
                "h1 tag not found or not a Tag instance."
            )

        return " ".join(h1.stripped_strings)

    @property
    def _url(self) -> str:
        url = urlsplit(self.feed.url)
        if url.hostname in {"shikimori.me", "shikimori.one"}:
            return urlunsplit(url._replace(netloc="shikimori.io"))
        return self.feed.url

    def _get_item_status(self, item: Tag) -> str:
        span_tag = item.find_all("span")[-1]
        if isinstance(span_tag, Tag):
            return span_tag.text
        raise ValueError
