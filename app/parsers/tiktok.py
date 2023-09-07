from app.serializers.feed import Item
from ._exceptions import UnavailableFeed
from .web import WebFeed


class TikTokFeed(WebFeed):
    __base_url = 'https://proxitok.pabloferreiro.es'

    @property
    async def items(self) -> list[Item]:
        url = f'{self.__base_url}/@{self._user_name}/rss'
        try:
            items = await self._get_items_from_web(url)
            return [self._normolize_item(i) for i in items]
        except (UnavailableFeed, ValueError):
            return []

    def _normolize_item(self, item: Item) -> str:
        base_url = 'https://www.tiktok.com/'
        relative_link = item.link
        if not self._is_link_relative(item.link):
            relative_link = item.link.split(self.__base_url)[1]
        item.link = base_url + relative_link
        return item

    def _is_link_relative(self, url: str) -> bool:
        return not url.startswith('http')

    @property
    def _user_name(self) -> str:
        return self.feed.url.split('@')[-1]
