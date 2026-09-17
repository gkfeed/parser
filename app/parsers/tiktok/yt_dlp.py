import logging

from app.core.worker_kind import WorkerKind
from app.services.ytdlp.extractor import YtdlpInfoExtractor
from app.services.ytdlp.modes import BaseExtractionMode

from ._base import BaseTikTokFeed

logger = logging.getLogger(__name__)


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
                    "TikTok entry skipped entry_index=%d reason=missing_url", index
                )
                continue
            videos.append(v["url"])
        logger.info(
            "TikTok discovery completed requested_limit=%d entries=%d links=%d "
            "skipped=%d below_limit=%s",
            self._max_videos,
            len(entries),
            len(videos),
            skipped,
            len(videos) < self._max_videos,
        )
        return videos
