from datetime import timedelta

from app.utils.datetime import constant_datetime
from app.utils.return_empty_when import async_return_empty_when
from app.serializers.feed import Item
from app.extentions.parsers.exceptions import UnavailableFeed
from app.extentions.parsers.http import HttpParserExtention


class KinogoFeed(HttpParserExtention):
    _cache_storage_time = timedelta(hours=1)

    @property
    @async_return_empty_when(UnavailableFeed, ValueError)
    async def items(self) -> list[Item]:
        title = await self._show_title
        status = await self._show_status
        return [
            Item(
                title=title + " " + status,
                text=status,
                date=constant_datetime,
                link=self.feed.url,
            )
        ]

    @property
    async def _show_status(self) -> str:
        try:
            soup = await self.get_soup(self.feed.url)
            return soup.find_all(class_="status7")[0].text
        except IndexError:
            raise ValueError

    @property
    async def _show_title(self) -> str:
        try:
            soup = await self.get_soup(self.feed.url)
            return soup.find_all("h1")[0].text
        except IndexError:
            raise ValueError("Couldn'n find status of show: " + self.feed.url)
