from asyncio import TaskGroup
from datetime import datetime
from typing import AsyncGenerator

from app.utils.datetime import convert_datetime
from app.utils.return_empty_when import async_return_empty_when
from app.serializers.feed import Item
from app.services.youtube import (
    BaseExtractionMode,
    ChannelExtractionMode,
    YoutubeInfoExtractor,
    PlaylistExtractionMode,
    VideoExtractionMode,
)
from app.extentions.parsers.exceptions import UnavailableFeed
from app.extentions.parsers.base import BaseFeed


class YoutubeFeed(BaseFeed):
    @property
    @async_return_empty_when(UnavailableFeed, ValueError)
    async def items(self) -> list[Item]:
        tasks = []
        async with TaskGroup() as tg:
            async for v in self._videos_infos:
                tasks.append(tg.create_task(self._create_video_item(v)))

        return [task.result() for task in tasks if task.result()]

    async def _create_video_item(self, video_info: dict) -> Item | None:
        try:
            return Item(
                title="YT: " + await self._channel_name,
                text=video_info["title"],
                date=await self._get_video_publish_date(video_info),
                link=video_info["webpage_url"],
            )
        except (TypeError, ValueError):
            return None

    @property
    async def _channel_name(self) -> str:
        target_url = self._get_target_url()
        info = await YoutubeInfoExtractor.get_info(target_url)
        return info["uploader"]

    @property
    async def _videos_infos(self) -> AsyncGenerator[dict, dict]:
        videos_url = self._get_target_url()
        extraction_mode = self._choose_extraction_mode(videos_url)
        max_videos = 5  # FIXME: feed options

        info = await YoutubeInfoExtractor.get_info(videos_url, extraction_mode)

        for video in info["entries"][-max_videos:]:
            yield video

    def _get_target_url(self) -> str:
        target_url = self.feed.url
        if target_url.split("/")[-1] == "channel":
            target_url += "/videos"
        return target_url

    def _choose_extraction_mode(self, url: str) -> BaseExtractionMode:
        if "playlist" in url:
            return PlaylistExtractionMode()
        return ChannelExtractionMode()

    async def _get_video_publish_date(self, video: dict) -> datetime:
        today_timestamp = datetime.today().timestamp()
        if "timestamp" in video and video["timestamp"] >= today_timestamp:
            date_str = datetime.fromtimestamp(video["timestamp"]).strftime("%Y%m%d")
            return convert_datetime(date_str)
        info = await YoutubeInfoExtractor.get_info(
            video["webpage_url"], VideoExtractionMode()
        )
        return convert_datetime(info["upload_date"])
