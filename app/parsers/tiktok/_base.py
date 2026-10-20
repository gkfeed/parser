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

        outcome = "items_extracted"
        if not items:
            outcome = "no_items_extracted" if links else "no_links"
        log = logger.warning if failed or skipped or not links else logger.info
        log(
            "tiktok_extraction_completed",
            outcome=outcome,
            links=len(links),
            items=len(items),
            failed=failed,
            skipped=skipped,
        )
        if failed:
            self.data["retry_at"] = datetime.now(UTC) + timedelta(minutes=15)
        if links and not items:
            raise ValueError("Could not extract any discovered TikTok videos")
        return items

    async def _create_video_item(self, link: str) -> Item | None:
        try:
            info = await self._get_video_info(link)
            return Item(
                title=info["description"],
                text=info["description"],
                date=await self._get_video_publish_date(info["timestamp"]),
                link=link,
            )
        except (KeyError, TypeError, ValueError) as exc:
            if not isinstance(exc, TikTokVideoRestricted):
                self.data["retry_at"] = datetime.now(UTC) + timedelta(minutes=15)
            logger.warning(
                "tiktok_video_skipped",
                reason="restricted"
                if isinstance(exc, TikTokVideoRestricted)
                else "invalid_video_data",
                error_type=type(exc).__name__,
                **url_log_fields(link, field="video_url"),
            )
            return None

    async def _get_video_info(self, link: str) -> dict[str, Any]:
        return await YtdlpInfoExtractor.get_info(link)

    @property
    @abstractmethod
    async def _video_links(self) -> list[str]:
        pass

    async def _get_video_publish_date(self, timestamp: float) -> datetime:
        date_str = datetime.fromtimestamp(timestamp, UTC).strftime("%Y%m%d %H:%M:%S")
        return parse_datetime(date_str)
