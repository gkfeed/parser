from urllib.parse import urlsplit, urlunsplit

from app.core.worker_kind import WorkerKind
from app.extensions.parsers.base import BaseFeed
from app.extensions.parsers.hash import ItemLinkHashExtension
from app.serializers.feed import Item
from app.services.youtube import YoutubePublishDateService
from app.services.ytdlp import (
    BaseExtractionMode,
    ChannelExtractionMode,
    PlaylistExtractionMode,
)
from app.services.ytdlp.extractor import YtdlpInfoExtractor


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


class YoutubeFeed(ItemLinkHashExtension, _BaseYoutubeFeed):
    worker_kind = WorkerKind.LIGHT

    async def _parse_items(self) -> list[Item]:
        videos_url = self._get_target_url()
        extraction_mode = self._choose_extraction_mode(self.feed.url)
        max_items = 5

        channel_info = await YtdlpInfoExtractor.extract_channel_videos_info(
            videos_url, extraction_mode, max_items
        )
        self._validate_channel_info(channel_info)

        entries = channel_info["entries"]
        if not entries:
            return []

        channel_name = channel_info["channel"]
        channel_id = channel_info.get("channel_id")
        channel_publish_dates = (
            await YoutubePublishDateService.get_channel_publish_dates(channel_id)
            if channel_id
            else {}
        )

        items = []
        for video_info in entries:
            title = video_info["title"]
            video_url = video_info.get("url") or video_info["webpage_url"]

            published_at = YoutubePublishDateService.resolve(
                video_info, channel_publish_dates
            )
            if published_at is None:
                raise ValueError(f"YouTube video has no publish date: {video_url}")

            items.append(
                Item(
                    title="YT: " + channel_name,
                    text=title,
                    date=published_at,
                    link=video_url,
                )
            )

        return items

    @staticmethod
    def _validate_channel_info(info: dict) -> None:
        if info.get("extraction_incomplete"):
            raise ValueError("YouTube extraction returned incomplete results")
        entries = info.get("entries")
        if not isinstance(entries, list):
            raise TypeError("YouTube extraction did not return an entries list")
        if not entries:
            return

        channel = info.get("channel")
        if not isinstance(channel, str) or not channel.strip():
            raise ValueError("YouTube extraction returned no channel name")
        for index, video in enumerate(entries, start=1):
            if not isinstance(video, dict):
                raise TypeError(f"YouTube extraction failed for video entry {index}")
            title = video.get("title")
            if not isinstance(title, str) or not title.strip():
                raise ValueError(f"YouTube video entry {index} has no title")
            link = video.get("url") or video.get("webpage_url")
            if not isinstance(link, str) or not link.strip():
                raise ValueError(f"YouTube video entry {index} has no usable link")
