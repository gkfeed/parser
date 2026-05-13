from typing import override
from bs4 import Tag

from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin


class PornHubFeed(PostToItemsMixin, HttpParserExtension):
    _base_url = "https://www.pornhub.com"

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)

        containers = []
        for section_id in [
            "claimedUploadedVideoSection",
            "modelMostRecentVideosSection",
            "claimedRecentVideoSection",
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
            return self._base_url + str(post["href"])
        raise ValueError("No link found in post")
