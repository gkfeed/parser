from datetime import timedelta

from app.utils.datetime import constant_datetime
from app.serializers.feed import Item
from ._exceptions import UnavailableFeed
from ._parser import WebParser


class YummyAnimeFeed(WebParser):
    _cache_storage_time = timedelta(hours=1)

    @property
    async def items(self) -> list[Item]:
        try:
            title = await self._show_title
            status = await self._show_status
            return [
                Item(
                    title=title + ' ' + status,
                    text=status,
                    date=constant_datetime,
                    link=self.feed.url,
                )
            ]
        except (UnavailableFeed, ValueError):
            return []

    @property
    async def _show_status(self) -> str:
        try:
            soup = await self.get_soup(self.feed.url)
            return soup.find_all(class_='anime-r')[1].text
        except IndexError:
            raise ValueError

    @property
    async def _show_title(self) -> str:
        try:
            soup = await self.get_soup(self.feed.url)
            return soup.find_all('h1')[0].text
        except IndexError:
            raise ValueError('Couldn\'n find status of show: ' + self.feed.url)
