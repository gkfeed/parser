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
            return [self._convert_item_link_to_absolute(i) for i in items]
        except (UnavailableFeed, ValueError):
            return []

    def _convert_item_link_to_absolute(self, item: Item) -> Item:
        item.link = self.__base_url + item.link
        return item

    @property
    def _user_name(self) -> str:
        return self.feed.url.split('@')[-1]
