from datetime import timedelta
from typing import Any, override
from urllib.parse import urljoin, urlparse

from bs4 import Tag

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.http import HttpParserExtension
from app.serializers.feed import Item
from app.services.http import HttpService
from app.utils.datetime import constant_datetime


class MatreshkaFeed(HttpParserExtension, CacheFeedExtension):
    _cache_storage_time = timedelta(days=1)
    _page_size = 12

    @property
    @override
    async def items(self) -> list[Item]:
        soup = await self.get_soup(self.feed.url)
        channel_title = self._extract_channel_title(soup)
        videos = await self._get_videos()

        return [
            Item(
                title=f"{channel_title} - {video['name']}",
                text=f"{channel_title} - {video['name']}",
                date=constant_datetime,
                link=urljoin(self.feed.url, f"/video/{video['id']}"),
            )
            for video in videos
            if video.get("id") and video.get("name")
        ]

    async def _get_videos(self) -> list[dict[str, Any]]:
        channel_id = self._extract_channel_id()
        api_url = urljoin(self.feed.url, "/api/v2/video")
        response = await HttpService.post_json(
            api_url,
            {
                "field_mask": ["id", "name"],
                "filter": [{"field": "channel_id", "is": "=", "value": channel_id}],
                "scope": ["public"],
                "page": 1,
                "per_page": self._page_size,
                "sort": {"field": "published_at", "direction": "desc"},
            },
            headers={
                **HttpService.headers,
                "Accept": "application/json, text/plain, */*",
                "Origin": self._get_origin(),
                "Referer": self.feed.url,
                "X-Request-Context": "default",
            },
        )
        videos = response.get("data", [])
        return videos if isinstance(videos, list) else []

    def _get_origin(self) -> str:
        parsed_url = urlparse(self.feed.url)
        return f"{parsed_url.scheme}://{parsed_url.netloc}"

    def _extract_channel_id(self) -> str:
        path_parts = urlparse(self.feed.url).path.strip("/").split("/")
        if len(path_parts) < 2 or path_parts[0] != "channel":
            raise ValueError("Could not find Matreshka channel ID in feed URL")
        return path_parts[1]

    def _extract_channel_title(self, soup: Tag) -> str:
        title_tag = soup.select_one("title")
        if title_tag and title_tag.text:
            return title_tag.text.split("|")[0].strip()
        return "Unknown Channel"
