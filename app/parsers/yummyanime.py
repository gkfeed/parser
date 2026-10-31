from typing import override
from urllib.parse import urlsplit, urlunsplit

from bs4 import Tag

from app.extensions.parsers.hash import ItemIdentityHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.utils.html import require_tag, required_text


class YummyAnimeFeed(PostToItemsMixin, ItemIdentityHashExtension, HttpParserExtension):
    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self._show_url)
        page_title = soup.find("title")
        title = (
            page_title.get_text(" ", strip=True).casefold()
            if isinstance(page_title, Tag)
            else ""
        )
        if title.startswith("страница не найдена") or title == "404 not found":
            raise ValueError("YummyAnime page not found: " + self._show_url)
        return [soup]

    @override
    async def _get_post_title(self, post: Tag) -> str:
        title = await self._show_title(post)
        status = await self._show_status(post)
        return f"{title} {status}"

    @override
    async def _get_post_text(self, post: Tag) -> str:
        return await self._show_status(post)

    @override
    async def _get_post_link(self, post: Tag) -> str:
        return self._show_url

    async def _show_status(self, soup: Tag) -> str:
        status = soup.select_one(".status-category div")
        if isinstance(status, Tag):
            return required_text(status, "YummyAnime show status", separator=" ")

        legacy_statuses = soup.find_all(class_="anime-r")
        if len(legacy_statuses) > 1:
            status = require_tag(legacy_statuses[1], "YummyAnime show status")
            return required_text(status, "YummyAnime show status", separator=" ")

        raise ValueError("Couldn't find status of show: " + self._show_url)

    async def _show_title(self, soup: Tag) -> str:
        title = require_tag(soup.find("h1"), "YummyAnime show title")
        return required_text(title, "YummyAnime show title", separator=" ")

    @property
    def _show_url(self) -> str:
        url = urlsplit(self.feed.url)
        if url.hostname not in {
            "yummyanime.org",
            "www.yummyanime.org",
            "site.yummyani.me",
            "old.yummyani.me",
        }:
            return self.feed.url

        netloc = url.netloc
        if url.hostname in {"yummyanime.org", "www.yummyanime.org"}:
            netloc = "site.yummyani.me"
            if url.port is not None:
                netloc += f":{url.port}"
        return urlunsplit(url._replace(netloc=netloc))
