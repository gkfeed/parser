import asyncio
from datetime import datetime, timedelta
from abc import ABC, abstractmethod

from app.utils.datetime import convert_datetime
from app.serializers.feed import Item
from app.workers.tiktok import extract_video_info
from app.extensions.parsers.base import BaseFeed as _BaseFeed
from app.extensions.parsers.cache import CacheFeedExtension


class BaseTikTokFeed(CacheFeedExtension, _BaseFeed, ABC):
    _cache_storage_time_if_success = timedelta(days=1)

    @property
    async def items(self) -> list[Item]:
        tasks = []
        async with asyncio.TaskGroup() as tg:
            for link in await self._video_links:
                tasks.append(tg.create_task(self._create_video_item(link)))

        return [task.result() for task in tasks if task.result()]

    async def _create_video_item(self, link: str) -> Item | None:
        try:
            description, url, timestamp = await extract_video_info(link)
            return Item(
                title=description,
                text=description,
                date=await self._get_video_publish_date(timestamp),
                link=self.feed.url + "/video/" + url.split("/")[-1],
            )
        except (TypeError, ValueError):
            return None

    @property
    @abstractmethod
    async def _video_links(self) -> list[str]:
        pass

    async def _get_video_publish_date(self, timestamp: float) -> datetime:
        date_str = datetime.fromtimestamp(timestamp).strftime("%Y%m%d %H:%M:%S")
        return convert_datetime(date_str)
