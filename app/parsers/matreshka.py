from datetime import timedelta
from typing import Any, override
from urllib.parse import urljoin, urlparse

from bs4 import Tag

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.exceptions import FeedUnavailable
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.serializers.feed import Item
from app.services.hash import HashService
from app.services.http import HttpRequestError, HttpService
from app.utils.datetime import constant_datetime


class MatreshkaFeed(ItemsHashExtension, HttpParserExtension, CacheFeedExtension):
    _cache_storage_time = timedelta(days=1)
    _page_size = 12

    @override
    async def _generate_hash(self, item: Item) -> str:
        return HashService.hash_str(item.link)

    @override
    async def _parse_items(self) -> list[Item]:
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
        ]

    async def _get_videos(self) -> list[dict[str, Any]]:
        channel_id = self._extract_channel_id()
        api_url = urljoin(self.feed.url, "/api/v2/video")
        try:
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
        except HttpRequestError as exc:
            raise FeedUnavailable(self.feed.url, "http_request_failed") from exc
        except ValueError as exc:
            raise ValueError(
                "Invalid Matreshka API response: expected valid JSON"
            ) from exc

        if not isinstance(response, dict):
            raise ValueError(  # noqa: TRY004 - malformed parser data is a value error
                "Invalid Matreshka API response: expected an object"
            )
        if "data" not in response:
            raise ValueError("Invalid Matreshka API response: missing 'data'")
        videos = response["data"]
        if not isinstance(videos, list):
            raise ValueError(  # noqa: TRY004 - malformed parser data is a value error
                "Invalid Matreshka API response: 'data' must be a list"
            )

        for index, video in enumerate(videos):
            if not isinstance(video, dict):
                raise ValueError(  # noqa: TRY004 - malformed parser data is a value error
                    f"Invalid Matreshka video at data[{index}]: expected an object"
                )
            video_id = video.get("id")
            if not isinstance(video_id, str) or not video_id.strip():
                raise ValueError(
                    f"Invalid Matreshka video at data[{index}]: "
                    "'id' must be a non-empty string"
                )
            name = video.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(
                    f"Invalid Matreshka video at data[{index}]: "
                    "'name' must be a non-empty string"
                )
        return videos

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
        channel_title = title_tag.text.split("|")[0].strip() if title_tag else ""
        if not channel_title:
            raise ValueError("Could not find Matreshka channel title in page")
        return channel_title
