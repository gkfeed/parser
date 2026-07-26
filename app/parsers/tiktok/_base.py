import asyncio
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import override

from app.extensions.parsers.base import BaseFeed as _BaseFeed
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemsHashExtension
from app.serializers.feed import Item
from app.services.hash import HashService
from app.services.ytdlp.extractor import YtdlpInfoExtractor
from app.utils.datetime import convert_datetime


class BaseTikTokFeed(ItemsHashExtension, CacheFeedExtension, _BaseFeed, ABC):
    _cache_storage_time_if_success = timedelta(days=1)

    @property
    async def items(self) -> list[Item]:
        links = await self._video_links
        results = await asyncio.gather(
            *(self._create_video_item(link) for link in links),
            return_exceptions=True,
        )

        items = []
        for link, result in zip(links, results, strict=True):
            if isinstance(result, BaseException):
                if not isinstance(result, Exception):
                    raise result
                print(f"Failed to extract TikTok video {link}: {result}")
            elif result is not None:
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
        date_str = datetime.fromtimestamp(timestamp, UTC).strftime("%Y%m%d %H:%M:%S")
        return convert_datetime(date_str)
