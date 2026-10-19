from datetime import timedelta
from typing import override
from urllib.parse import urljoin

from bs4 import Tag

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemLinkHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.serializers.feed import Item
from app.services.matreshka import MatreshkaClient
from app.utils.datetime import constant_datetime


class MatreshkaFeed(ItemLinkHashExtension, HttpParserExtension, CacheFeedExtension):
    _cache_storage_time = timedelta(days=1)
    _page_size = 12

    @override
    async def _parse_items(self) -> list[Item]:
        soup = await self.get_soup(self.feed.url)
        channel_title = self._extract_channel_title(soup)
        videos = await MatreshkaClient(self.feed.url).get_videos(self._page_size)

        return [
            Item(
                title=f"{channel_title} - {video['name']}",
                text=f"{channel_title} - {video['name']}",
                date=constant_datetime,
                link=urljoin(self.feed.url, f"/video/{video['id']}"),
            )
            for video in videos
        ]

    def _extract_channel_title(self, soup: Tag) -> str:
        title_tag = soup.select_one("title")
        if title_tag and title_tag.text:
            return title_tag.text.split("|")[0].strip()
        return "Unknown Channel"
