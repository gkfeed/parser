from datetime import UTC, datetime
from typing import Any, ClassVar

from app.core.worker_kind import WorkerKind
from app.extensions.parsers.base import BaseFeed
from app.extensions.parsers.hash import ItemsHashExtension
from app.serializers.feed import Item
from app.services.hash import HashService
from app.services.ytdlp import BaseExtractionMode, YtdlpInfoExtractor
from app.utils.datetime import constant_datetime


class VkVideoExtractionMode(BaseExtractionMode):
    opts: ClassVar[dict[str, Any]] = {
        **BaseExtractionMode.opts,
        "extract_flat": False,
        "skip_download": True,
    }


class VkVideoFeed(ItemsHashExtension, BaseFeed):
    worker_kind = WorkerKind.LIGHT
    _max_videos = 5

    async def _parse_items(self) -> list[Item]:
        info = await YtdlpInfoExtractor.extract_channel_videos_info(
            self.feed.url, VkVideoExtractionMode(), self._max_videos
        )
        channel = info.get("title") or self.feed.title
        items = []
        for video in info["entries"]:
            if not video:
                continue

            video_id = video.get("id")
            link = (
                f"https://vkvideo.ru/video{video_id}"
                if video_id
                else video.get("webpage_url") or video.get("url")
            )
            if not link:
                continue

            timestamp = video.get("timestamp") or video.get("release_timestamp")
            upload_date = video.get("upload_date")
            if timestamp:
                published_at = datetime.fromtimestamp(timestamp, UTC)
            elif upload_date:
                published_at = datetime.strptime(upload_date, "%Y%m%d").replace(
                    tzinfo=UTC
                )
            else:
                published_at = constant_datetime

            items.append(
                Item(
                    title=f"VK Video: {channel}",
                    text=video.get("title") or "VK Video",
                    date=published_at,
                    link=link,
                )
            )

        return items

    async def _generate_hash(self, item: Item) -> str:
        return HashService.hash_str(item.link)
