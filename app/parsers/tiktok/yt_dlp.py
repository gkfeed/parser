import structlog

from app.core.worker_kind import WorkerKind
from app.services.ytdlp.extractor import YtdlpInfoExtractor
from app.services.ytdlp.modes import BaseExtractionMode

from ._base import BaseTikTokFeed

logger = structlog.get_logger(__name__)


class TikTokFeed(BaseTikTokFeed):
    worker_kind = WorkerKind.LIGHT
    _max_videos = 10

    @property
    async def _video_links(self) -> list[str]:
        info = await YtdlpInfoExtractor.extract_channel_videos_info(
            self.feed.url, BaseExtractionMode(), self._max_videos
        )

        entries = info["entries"]
        videos: list[str] = []
        skipped = 0
        for index, v in enumerate(entries, start=1):
            if len(videos) >= self._max_videos:
                break
            if "url" not in v:
                skipped += 1
                logger.warning(
                    "tiktok_entry_skipped", entry_index=index, reason="missing_url"
                )
                continue
            videos.append(v["url"])
        logger.info(
            "tiktok_discovery_completed",
            requested_limit=self._max_videos,
            entries=len(entries),
            links=len(videos),
            skipped=skipped,
            below_limit=len(videos) < self._max_videos,
        )
        return videos
