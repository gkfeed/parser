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
        url_parts = target_url.split("/")
        if url_parts[-2] == "channel" or len(target_url.split("@")) == 2:
            target_url += "/videos"
        return target_url


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
            await YoutubePublishDateService.get_channel_publish_dates(channel_id)
            if channel_id
            else {}
        )

        items = []
        for video_info in entries:
            title = video_info["title"]
            video_url = video_info["url"]

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
