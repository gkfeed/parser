import asyncio
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from app.extensions.parsers.base import BaseFeed as _BaseFeed
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemLinkHashExtension
from app.serializers.feed import Item
from app.services.ytdlp.extractor import YtdlpInfoExtractor
from app.services.ytdlp.tiktok import TikTokVideoRestricted
from app.utils.datetime import parse_datetime
from app.utils.logging import url_log_fields

logger = structlog.get_logger(__name__)


class BaseTikTokFeed(ItemLinkHashExtension, CacheFeedExtension, _BaseFeed, ABC):
    _cache_storage_time_if_success = timedelta(days=1)

    async def _parse_items(self) -> list[Item]:
        links = await self._video_links
        tasks = [asyncio.create_task(self._create_video_item(link)) for link in links]
        try:
            results = await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

        items = []
        skipped = 0
        for result in results:
            if result is None:
                skipped += 1
                continue

            items.append(result)

        outcome = "items_extracted"
        if not items:
            outcome = "no_items_extracted" if links else "no_links"
        log = logger.warning if skipped or not links else logger.info
        log(
            "tiktok_extraction_completed",
            outcome=outcome,
            links=len(links),
            items=len(items),
            skipped=skipped,
        )
        if links and not items:
            raise ValueError("Could not extract any discovered TikTok videos")
        return items

    async def _create_video_item(self, link: str) -> Item | None:
        try:
            info = await self._get_video_info(link)
        except TikTokVideoRestricted as exc:
            logger.warning(
                "tiktok_video_skipped",
                reason="restricted",
                error_type=type(exc).__name__,
                **url_log_fields(link, field="video_url"),
            )
            return None
        return Item(
            title=info["description"],
            text=info["description"],
            date=await self._get_video_publish_date(info["timestamp"]),
            link=link,
        )

    async def _get_video_info(self, link: str) -> dict[str, Any]:
        return await YtdlpInfoExtractor.get_info(link)

    @property
    @abstractmethod
    async def _video_links(self) -> list[str]:
        pass

    async def _get_video_publish_date(self, timestamp: float) -> datetime:
        date_str = datetime.fromtimestamp(timestamp, UTC).strftime("%Y%m%d %H:%M:%S")
        return parse_datetime(date_str)
