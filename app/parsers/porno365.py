from typing import override
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import Tag

from app.extensions.parsers.hash import ItemLinkHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.utils.html import require_tag, required_attr, required_text


class Porno365Feed(PostToItemsMixin, ItemLinkHashExtension, HttpParserExtension):
    _canonical_scheme = "http"
    _canonical_host = "porno365.broker"

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)
        container = require_tag(
            soup.find("ul", class_="videos_ul"), "Porno365 video list"
        )

        return [
            post
            for post in container.find_all("li", class_="video_block")
            if isinstance(post, Tag)
        ]

    @override
    async def _get_post_title(self, post: Tag) -> str:
        title = post.find("p")
        if isinstance(title, Tag):
            return required_text(title, "Porno365 post title", separator=" ")

        image = require_tag(post.find("img"), "Porno365 post title")
        image_title = required_attr(image, "alt", "Porno365 post title").strip()
        if not image_title:
            raise ValueError("Empty alt text for Porno365 post title")
        return image_title

    @override
    async def _get_post_link(self, post: Tag) -> str:
        link = require_tag(post.find("a", class_="image"), "Porno365 post link")
        href = required_attr(link, "href", "Porno365 post link")
        parsed_link = urlsplit(urljoin(self.feed.url, href))
        return urlunsplit(
            (
                self._canonical_scheme,
                self._canonical_host,
                parsed_link.path,
                parsed_link.query,
                parsed_link.fragment,
            )
        )
