from app.serializers.feed import Item
from app.utils.datetime import constant_datetime

from app.extensions.parsers.selenium import SeleniumParserExtension


class RezkaFeed(SeleniumParserExtension):
    @property
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
        title = soup.find("h1").text
        seasons = soup.find_all(class_="b-simple_season__item")
        episodes_tabs = soup.find_all(id="simple-episodes-tabs")
        return f"{title} {seasons[-1].text} {episodes_tabs[-1].find_all('li')[-1].text}"
