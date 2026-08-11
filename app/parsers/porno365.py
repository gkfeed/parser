from typing import override
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import Tag

from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.serializers.feed import Item
from app.services.hash import HashService


class Porno365Feed(PostToItemsMixin, ItemsHashExtension, HttpParserExtension):
    _canonical_scheme = "http"
    _canonical_host = "porno365.broker"

    @override
    async def _generate_hash(self, item: Item) -> str:
        return HashService.hash_str(item.link)

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)
        container = soup.find("ul", class_="videos_ul")
        if not isinstance(container, Tag):
            raise ValueError(  # noqa: TRY004 - missing page data is a value error
                "Video list not found"
            )

        return [
            post
            for post in container.find_all("li", class_="video_block")
            if isinstance(post, Tag)
        ]

    @override
    async def _get_post_title(self, post: Tag) -> str:
        title = post.find("p")
        if title:
            return title.text.strip()

        image = post.find("img")
        if isinstance(image, Tag) and "alt" in image.attrs:
            return str(image["alt"]).strip()

        raise ValueError("No title found in post")

    @override
    async def _get_post_link(self, post: Tag) -> str:
        link = post.find("a", class_="image")
        if isinstance(link, Tag) and "href" in link.attrs:
            parsed_link = urlsplit(urljoin(self.feed.url, str(link["href"])))
            return urlunsplit(
                (
                    self._canonical_scheme,
                    self._canonical_host,
                    parsed_link.path,
                    parsed_link.query,
                    parsed_link.fragment,
                )
            )
        raise ValueError("No link found in post")
