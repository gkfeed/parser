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
        except ValueError as error:
            raise ValueError(
                "Invalid Matreshka API response: expected valid JSON"
            ) from error

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
