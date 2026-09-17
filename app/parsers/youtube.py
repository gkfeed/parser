from urllib.parse import urlsplit, urlunsplit

from app.core.worker_kind import WorkerKind
from app.extensions.parsers.base import BaseFeed
from app.extensions.parsers.hash import ItemsHashExtension
from app.serializers.feed import Item
from app.services.hash import HashService
from app.services.youtube import YoutubePublishDateService
from app.services.ytdlp import (
    BaseExtractionMode,
    ChannelExtractionMode,
    PlaylistExtractionMode,
)
from app.services.ytdlp.extractor import YtdlpInfoExtractor
from app.utils.datetime import constant_datetime


class _BaseYoutubeFeed(BaseFeed):
    def _choose_extraction_mode(self, url: str) -> BaseExtractionMode:
        if "playlist" in url:
            return PlaylistExtractionMode()
        return ChannelExtractionMode()

    def _get_target_url(self) -> str:
        target_url = self.feed.url
        parsed_url = urlsplit(target_url)
        path_parts = [part for part in parsed_url.path.split("/") if part]
        is_handle_root = len(path_parts) == 1 and path_parts[0].startswith("@")
        is_channel_id_root = len(path_parts) == 2 and path_parts[0] == "channel"

        if not (is_handle_root or is_channel_id_root):
            return target_url

        videos_path = parsed_url.path.rstrip("/") + "/videos"
        return urlunsplit(parsed_url._replace(path=videos_path))


class YoutubeFeed(ItemsHashExtension, _BaseYoutubeFeed):
    worker_kind = WorkerKind.LIGHT

    @property
    async def items(self) -> list[Item]:
        videos_url = self._get_target_url()
        extraction_mode = self._choose_extraction_mode(self.feed.url)
        max_items = 5

        channel_info = await YtdlpInfoExtractor.extract_channel_videos_info(
            videos_url, extraction_mode, max_items
        )

        channel_name = channel_info["channel"]
        entries = channel_info["entries"]
        channel_id = channel_info.get("channel_id")
        channel_publish_dates = (
            await YoutubePublishDateService.get_channel_publish_dates(
                self.http, channel_id
            )
            if channel_id
            else {}
        )

        items = []
        for video_info in entries:
            if video_info is None:
                continue

            title = video_info["title"]
            video_url = video_info.get("url") or video_info["webpage_url"]

            published_at = YoutubePublishDateService.resolve(
                video_info, channel_publish_dates
            )

            items.append(
                Item(
                    title="YT: " + channel_name,
                    text=title,
                    date=published_at or constant_datetime,
                    link=video_url,
                )
            )

        return items

    async def _generate_hash(self, item: Item) -> str:
        return HashService.hash_str(item.link)
