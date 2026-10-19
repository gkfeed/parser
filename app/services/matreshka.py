from typing import Any
from urllib.parse import urljoin, urlparse

from app.extensions.parsers.exceptions import FeedUnavailable
from app.services.http import HttpRequestError, HttpService


class MatreshkaClient:
    def __init__(self, channel_url: str) -> None:
        self._channel_url = channel_url

    async def get_videos(self, page_size: int) -> list[dict[str, Any]]:
        path_parts = urlparse(self._channel_url).path.strip("/").split("/")
        if len(path_parts) < 2 or path_parts[0] != "channel":
            raise ValueError("Could not find Matreshka channel ID in feed URL")
        channel_id = path_parts[1]
        parsed_url = urlparse(self._channel_url)
        origin = f"{parsed_url.scheme}://{parsed_url.netloc}"
        try:
            response = await HttpService.post_json(
                urljoin(self._channel_url, "/api/v2/video"),
                {
                    "field_mask": ["id", "name"],
                    "filter": [{"field": "channel_id", "is": "=", "value": channel_id}],
                    "scope": ["public"],
                    "page": 1,
                    "per_page": page_size,
                    "sort": {"field": "published_at", "direction": "desc"},
                },
                headers={
                    **HttpService.headers,
                    "Accept": "application/json, text/plain, */*",
                    "Origin": origin,
                    "Referer": self._channel_url,
                    "X-Request-Context": "default",
                },
            )
        except HttpRequestError as error:
            raise FeedUnavailable(self._channel_url, "http_request_failed") from error

        # Preserve the existing payload policy here. Audit task 05 owns stricter
        # validation, including the distinction between missing and empty data.
        videos = response.get("data", [])
        if not isinstance(videos, list):
            return []
        return [video for video in videos if video.get("id") and video.get("name")]
