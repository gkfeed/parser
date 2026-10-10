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
        for index, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                logger.warning(
                    "tiktok_entry_skipped",
                    entry_index=index,
                    reason="invalid_entry_type",
                    entry_type=type(entry).__name__,
                )
                continue
            url = entry.get("url")
            if not isinstance(url, str) or not url.strip():
                logger.warning(
                    "tiktok_entry_skipped", entry_index=index, reason="invalid_url"
                )
                continue
            videos.append(url)

        skipped = len(entries) - len(videos)
        outcome = "links_found"
        if not videos:
            outcome = "no_valid_entries" if entries else "no_entries"
        log = logger.warning if skipped or not videos else logger.info
        log(
            "tiktok_discovery_completed",
            outcome=outcome,
            requested_limit=self._max_videos,
            entries=len(entries),
            links=len(videos),
            skipped=skipped,
            below_limit=len(videos) < self._max_videos,
        )
        if entries and not videos:
            raise ValueError("TikTok discovery returned no valid video links")
        return videos
