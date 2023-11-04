from datetime import timedelta

from app.serializers.feed import Item
from app.extentions.parsers.cache import (
    CacheFeedExtention,
    async_store_in_cache_if_not_empty_for,
)
from ..web import WebFeed
from ._base import BaseTikTokFeed


class TikTokFeed(BaseTikTokFeed, WebFeed, CacheFeedExtention):
    __base_url = "https://tok.adminforge.de"

    @property
    @async_store_in_cache_if_not_empty_for(timedelta(hours=2))
    async def _video_links(self) -> list[str]:
        url = f"{self.__base_url}/@{self._user_name}/rss"
        items = await self._get_items_from_web(url)

        links = []
        for item in items:
            link = self._normolize_item(item).link
            if link.startswith(self.feed.url):
                links.append(link)

        return links

    def _normolize_item(self, item: Item) -> Item:
        base_url = "https://www.tiktok.com"
        relative_link = item.link
        if not self._is_link_relative(item.link):
            relative_link = item.link.split(self.__base_url)[1]
        item.link = base_url + relative_link
        return item

    def _is_link_relative(self, url: str) -> bool:
        return not url.startswith("http")

    @property
    def _user_name(self) -> str:
        return self.feed.url.split("@")[-1]
