import asyncio
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
from typing import override

from app.utils.datetime import convert_datetime
from app.serializers.feed import Item

from app.services.ytdlp.extractor import YtdlpInfoExtractor
from app.services.hash import HashService
from app.extensions.parsers.base import BaseFeed as _BaseFeed
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemsHashExtension


class BaseTikTokFeed(ItemsHashExtension, CacheFeedExtension, _BaseFeed, ABC):
    _cache_storage_time_if_success = timedelta(days=1)

    @property
    async def items(self) -> list[Item]:
        tasks = []
        async with asyncio.TaskGroup() as tg:
            for link in await self._video_links:
                tasks.append(tg.create_task(self._create_video_item(link)))

        items = []
        for task in tasks:
            result = task.result()
            if result is not None and isinstance(result, Item):
                items.append(result)
        return items

    @override
    async def _generate_hash(self, item: Item) -> str:
        return HashService.hash_str(item.link)

    async def _create_video_item(self, link: str) -> Item | None:
        try:
            info = await YtdlpInfoExtractor.get_info(link)
            return Item(
                title=info["description"],
                text=info["description"],
                date=await self._get_video_publish_date(info["timestamp"]),
                link=link,
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
