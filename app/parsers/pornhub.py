from bs4 import Tag

from app.utils.datetime import constant_datetime
from app.serializers.feed import Item
from app.extensions.parsers.http import HttpParserExtension


class PornHubFeed(HttpParserExtension):
    _base_url = "https://www.pornhub.com"

    @property
    async def items(self) -> list[Item]:
        return [
            Item(
                title=self._get_video_title(p),
                text=self._get_video_title(p),
                date=constant_datetime,
                link=self._get_video_link(p),
            )
            for p in await self._posts
        ]

    @property
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

                link = self._get_video_link(p)
                if link in seen_links:
                    continue

                posts.append(p)
                seen_links.add(link)

        return posts

    def _get_video_title(self, post: Tag) -> str:
        if post.img and "title" in post.img.attrs:
            return str(post.img["title"])
        raise ValueError("No title found in post")

    def _get_video_link(self, post: Tag) -> str:
        if "href" in post.attrs:
            return self._base_url + str(post["href"])
        raise ValueError("No link found in post")
