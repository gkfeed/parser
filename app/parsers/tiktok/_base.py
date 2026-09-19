import asyncio
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import override

import structlog

from app.extensions.parsers.base import BaseFeed as _BaseFeed
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemsHashExtension
from app.serializers.feed import Item
from app.services.hash import HashService
from app.services.ytdlp.extractor import YtdlpInfoExtractor
from app.utils.datetime import convert_datetime
from app.utils.logging import url_log_fields

logger = structlog.get_logger(__name__)


class BaseTikTokFeed(ItemsHashExtension, CacheFeedExtension, _BaseFeed, ABC):
    _cache_storage_time_if_success = timedelta(days=1)

    async def _parse_items(self) -> list[Item]:
        links = await self._video_links
        results = await asyncio.gather(
            *(self._create_video_item(link) for link in links),
            return_exceptions=True,
        )

        items = []
        failed = 0
        skipped = 0
        for link, result in zip(links, results, strict=True):
            if result is None:
                skipped += 1
                continue

            if isinstance(result, Exception):
                failed += 1
                logger.error(
                    "tiktok_video_failed",
                    reason="extraction_error",
                    exc_info=result,
                    **url_log_fields(link, field="video_url"),
                )
                continue

            if isinstance(result, BaseException):
                raise result

            items.append(result)

        log = logger.warning if failed or skipped else logger.info
        log(
            "tiktok_extraction_completed",
            links=len(links),
            items=len(items),
            failed=failed,
            skipped=skipped,
        )
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
        except (TypeError, ValueError) as exc:
            logger.warning(
                "tiktok_video_skipped",
                reason="invalid_video_data",
                error_type=type(exc).__name__,
                **url_log_fields(link, field="video_url"),
            )
            return None

    @property
    @abstractmethod
    async def _video_links(self) -> list[str]:
        pass

    async def _get_video_publish_date(self, timestamp: float) -> datetime:
        date_str = datetime.fromtimestamp(timestamp, UTC).strftime("%Y%m%d %H:%M:%S")
        return convert_datetime(date_str)
