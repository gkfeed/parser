from asyncio import TaskGroup
from typing import AsyncGenerator

from app.utils.datetime import convert_datetime
from app.serializers.feed import Item
from app.services.youtube import (
    BaseExtractionMode,
    ChannelExtractionMode,
    PlaylistExtractionMode,
)
from app.extentions.parsers.base import BaseFeed
from app.workers.youtube import (
    extract_video_urls,
    extract_video_info,
)


class YoutubeFeed(BaseFeed):
    @property
    async def items(self) -> list[Item]:
        tasks = []
        async with TaskGroup() as tg:
            async for v in self._video_urls:
                tasks.append(tg.create_task(self._create_video_item(v)))

        return [task.result() for task in tasks if task.result()]

    async def _create_video_item(self, video_url: str) -> Item | None:
        try:
            title, date_str, channel_name = await extract_video_info(video_url)
            item = Item(
                title="YT: " + channel_name,
                text=title,
                date=convert_datetime(date_str),
                link=video_url,
            )
            return item
        except (TypeError, ValueError):
            return None

    @property
    async def _video_urls(self) -> AsyncGenerator[str, str]:
        videos_url = self._get_target_url()
        extraction_mode = self._choose_extraction_mode(videos_url)
        max_videos = 5  # FIXME: feed options
        for url in await extract_video_urls(videos_url, extraction_mode, max_videos):
            yield url

    def _get_target_url(self) -> str:
        target_url = self.feed.url
        if target_url.split("/")[-2] == "channel" or len(target_url.split("@")) == 2:
            target_url += "/videos"
        return target_url

    def _choose_extraction_mode(self, url: str) -> BaseExtractionMode:
        if "playlist" in url:
            return PlaylistExtractionMode()
        return ChannelExtractionMode()
