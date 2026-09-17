import asyncio
import logging
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
from app.utils.logging import log_context, log_url

logger = logging.getLogger(__name__)


class BaseTikTokFeed(ItemsHashExtension, CacheFeedExtension, _BaseFeed, ABC):
    _cache_storage_time_if_success = timedelta(days=1)

    @property
    async def items(self) -> list[Item]:
        with log_context(feed_id=self.feed.id, parser=type(self).__name__):
            links = await self._video_links
            results = await asyncio.gather(
                *(self._create_video_item(link) for link in links),
                return_exceptions=True,
            )

            items = []
            failed = 0
            skipped = 0
            for link, result in zip(links, results, strict=True):
                if isinstance(result, BaseException):
                    if not isinstance(result, Exception):
                        raise result
                    failed += 1
                    logger.error(
                        "TikTok video failed video_url=%s reason=extraction_error",
                        log_url(link),
                        exc_info=(type(result), result, result.__traceback__),
                    )
                elif result is not None:
                    items.append(result)
                else:
                    skipped += 1
            logger.log(
                logging.WARNING if failed or skipped else logging.INFO,
                "TikTok extraction completed links=%d items=%d failed=%d skipped=%d",
                len(links),
                len(items),
                failed,
                skipped,
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
        except (TypeError, ValueError):
            logger.warning(
                "TikTok video skipped video_url=%s reason=invalid_video_data",
                log_url(link),
                exc_info=True,
            )
            return None

    @property
    @abstractmethod
    async def _video_links(self) -> list[str]:
        pass

    async def _get_video_publish_date(self, timestamp: float) -> datetime:
        date_str = datetime.fromtimestamp(timestamp, UTC).strftime("%Y%m%d %H:%M:%S")
        return convert_datetime(date_str)
