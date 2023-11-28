import asyncio
from datetime import datetime
from abc import ABC, abstractmethod

from app.utils.return_empty_when import async_return_empty_when
from app.utils.datetime import convert_datetime
from app.serializers.feed import Item
from app.extentions.parsers.exceptions import UnavailableFeed
from app.extentions.parsers.base import BaseFeed as _BaseFeed
from app.services.tiktok import TikTokInfoExtractor


class BaseTikTokFeed(_BaseFeed, ABC):
    @property
    @async_return_empty_when(UnavailableFeed, ValueError)
    async def items(self) -> list[Item]:
        tasks = []
        async with asyncio.TaskGroup() as tg:
            for link in await self._video_links:
                tasks.append(tg.create_task(TikTokInfoExtractor.get_info(link)))

        items = []
        for task in tasks:
            info = task.result()
            items.append(
                Item(
                    title=info["description"],
                    text=info["description"],
                    date=await self._get_video_publish_date(info),
                    link=self.feed.url + "/video/" + info["webpage_url"].split("/")[-1],
                )
            )

        return items

    @property
    @abstractmethod
    def _video_links(self) -> list[str]:
        pass

    async def _get_video_publish_date(self, video: dict) -> datetime:
        date_str = datetime.fromtimestamp(video["timestamp"]).strftime(
            "%Y%m%d %H:%M:%S"
        )
        return convert_datetime(date_str)
