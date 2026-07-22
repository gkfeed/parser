from itertools import chain
from typing import override
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.serializers.feed import Item
from app.services.hash import HashService


class PornHubFeed(PostToItemsMixin, ItemsHashExtension, SeleniumParserExtension):
    _base_url = "https://www.pornhub.com"
    _video_section_ids = (
        "claimedUploadedVideoSection",
        "modelMostRecentVideosSection",
        "claimedRecentVideoSection",
        "uploadedVideosSection",
        "mostRecentVideosSection",
        "pornstarsVideoSection",
        "showAllChanelVideos",
    )

    @override
    async def _generate_hash(self, item: Item) -> str:
        return HashService.hash_str(item.link)

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self._get_posts_url())
        containers = self._find_post_containers(soup)
        return await self._collect_posts(containers)

    def _find_post_containers(self, soup: BeautifulSoup) -> list[Tag]:
        containers = []
        for section_id in self._video_section_ids:
            container = soup.find("ul", id=section_id)
            if isinstance(container, Tag):
                containers.append(container)

        if not containers:
            raise ValueError("Videosection not found")
        return containers

    async def _collect_posts(self, containers: list[Tag]) -> list[Tag]:
        posts = []
        seen_links = set()
        posts_in_containers = chain.from_iterable(
            container.find_all("a", class_="linkVideoThumb")
            for container in containers
        )
        for post in posts_in_containers:
            if not isinstance(post, Tag):
                continue

            if "href" not in post.attrs:
                continue

            try:
                await self._get_post_title(post)
            except ValueError:
                continue

            link = await self._get_post_link(post)
            if link in seen_links:
                continue

            posts.append(post)
            seen_links.add(link)
        return posts

    @override
    async def _get_post_title(self, post: Tag) -> str:
        image = post.find("img")
        if isinstance(image, Tag):
            for attribute in ("title", "data-title", "alt"):
                title = image.attrs.get(attribute)
                if title and str(title).strip():
                    return str(title).strip()
        raise ValueError("No title found in post")

    @override
    async def _get_post_link(self, post: Tag) -> str:
        if "href" in post.attrs:
            return self._get_base_url() + str(post["href"])
        raise ValueError("No link found in post")

    def _get_posts_url(self) -> str:
        url = self.feed.url.rstrip("/")
        path = urlparse(url).path
        if path.startswith(("/channels/", "/model/")):
            return f"{url}/videos"
        return self.feed.url

    def _get_base_url(self) -> str:
        parsed_url = urlparse(self.feed.url)
        if parsed_url.scheme and parsed_url.netloc:
            return f"{parsed_url.scheme}://{parsed_url.netloc}"
        return self._base_url
