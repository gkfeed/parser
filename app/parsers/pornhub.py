from typing import override
from urllib.parse import urlparse

from bs4 import Tag

from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.extensions.parsers.selenium import SeleniumParserExtension


class PornHubFeed(PostToItemsMixin, SeleniumParserExtension):
    _base_url = "https://www.pornhub.com"

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self._get_posts_url())

        containers = []
        for section_id in [
            "claimedUploadedVideoSection",
            "modelMostRecentVideosSection",
            "claimedRecentVideoSection",
            "uploadedVideosSection",
            "mostRecentVideosSection",
            "pornstarsVideoSection",
            "showAllChanelVideos",
        ]:
            container = soup.find("ul", id=section_id)
            if not isinstance(container, Tag):
                continue
            containers.append(container)

        if not containers:
            raise ValueError("Videosection not found")

        posts = []
        seen_links = set()
        for container in containers:
            for p in container.find_all("a", class_="linkVideoThumb"):
                if not isinstance(p, Tag):
                    continue

                if "href" not in p.attrs:
                    continue

                if not p.img or "title" not in p.img.attrs:
                    continue

                link = await self._get_post_link(p)
                if link in seen_links:
                    continue

                posts.append(p)
                seen_links.add(link)
        return posts

    @override
    async def _get_post_title(self, post: Tag) -> str:
        if post.img and "title" in post.img.attrs:
            return str(post.img["title"])
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
