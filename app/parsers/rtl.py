from typing import override
from urllib.parse import urljoin

from bs4 import Tag

from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin


class RTLSeriesFeed(PostToItemsMixin, HttpParserExtension):
    _base_url = "https://plus.rtl.de"

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)
        return [
            link
            for link in soup.find_all("a", href=True)
            if isinstance(link, Tag) and self._is_free_episode_link(link)
        ]

    @staticmethod
    def _is_free_episode_link(link: Tag) -> bool:
        card = link.find_parent("article")
        is_locked = isinstance(card, Tag) and card.find(
            attrs={"aria-label": "Blockierter Inhalt"}
        )
        return (
            "/video/" in str(link["href"])
            and link.find("p") is not None
            and not is_locked
        )

    @override
    async def _get_post_title(self, post: Tag) -> str:
        paragraphs = post.find_all("p")
        if paragraphs:
            return paragraphs[-1].get_text(" ", strip=True)
        raise ValueError("Episode link does not contain a title")

    @override
    async def _get_post_link(self, post: Tag) -> str:
        href = post.get("href")
        if isinstance(href, str):
            return urljoin(self._base_url, href)
        raise ValueError("Link element does not contain a valid href")
