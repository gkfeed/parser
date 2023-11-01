from app.serializers.feed import Item
from app.utils.datetime import constant_datetime
from app.utils.return_empty_when import async_return_empty_when
from app.extentions.parsers.exceptions import UnavailableFeed
from app.extentions.parsers.selenium import SeleniumParserExtention


class RezkaFeed(SeleniumParserExtention):
    @property
    @async_return_empty_when(UnavailableFeed, ValueError, TypeError)
    async def items(self) -> list[Item]:
        show_url = self.feed.url
        return [
            Item(
                title=await self._show_status,
                link=show_url,
                text=await self._show_status,
                date=constant_datetime,
            )
        ]

    @property
    async def _show_status(self) -> str:
        soup = await self.get_soup(self.feed.url)
        return soup.find_all("h2")[-1].text
