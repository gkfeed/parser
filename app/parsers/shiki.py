from datetime import timedelta, datetime

from bs4.element import Tag

from app.utils.datetime import convert_datetime
from app.serializers.feed import Item
from ._exceptions import UnavailableFeed
from ._parser import WebParser


class ShikiFeed(WebParser):
    _cache_storage_time = timedelta(hours=1)

    @property
    async def items(self) -> list[Item]:
        try:
            soup = await self.get_soup(self.feed.url)
            title = await self._show_title
            news = soup.find_all(
                class_='b-menu-links')[0].find_all(class_='entry')
            return [
                Item(
                    title=title + ' ' + self._get_item_status(item),
                    text=self._get_item_status(item),
                    date=self._get_item_date(item),
                    link=self.feed.url,
                )
                for item in news
            ]
        except (UnavailableFeed, ValueError, IndexError):
            # print('FAILED: ', self.feed.url)
            # import traceback
            # traceback.print_exc()
            return []

    @property
    async def _show_title(self) -> str:
        try:
            soup = await self.get_soup(self.feed.url)
            return soup.find_all('h1')[0].text
        except IndexError:
            raise ValueError

    def _get_item_status(self, item: Tag) -> str:
        try:
            return item.find_all('span')[1].text
        except IndexError:
            raise ValueError

    def _get_item_date(self, item: Tag) -> datetime:
        try:
            datetime_str = item.find_all('span')[0].time['datetime']
            return convert_datetime(datetime_str)
        except IndexError:
            raise ValueError
