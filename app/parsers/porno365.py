from typing import override
from urllib.parse import urljoin

from bs4 import Tag

from app.serializers.feed import Item
from app.services.hash import HashService
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin


class Porno365Feed(PostToItemsMixin, ItemsHashExtension, HttpParserExtension):
    @override
    async def _generate_hash(self, item: Item) -> str:
        return HashService.hash_str(item.link)

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)
        container = soup.find("ul", class_="videos_ul")
        if not isinstance(container, Tag):
            raise ValueError("Video list not found")

        posts = []
        for post in container.find_all("li", class_="video_block"):
            if not isinstance(post, Tag):
                continue

            posts.append(post)
        return posts

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
            return urljoin(self.feed.url, str(link["href"]))
        raise ValueError("No link found in post")
