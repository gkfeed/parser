from app.utils.datetime import constant_datetime
from app.serializers.feed import Item
from app.extensions.parsers.http import HttpParserExtension


class YummyAnimeFeed(HttpParserExtension):
    @property
    async def items(self) -> list[Item]:
        title = await self._show_title
        status = await self._show_status
        return [
            Item(
                title=title + " " + status,
                text=status,
                date=constant_datetime,
                link=self._show_url,
            )
        ]

    @property
    async def _show_status(self) -> str:
        try:
            soup = await self.get_soup(self._show_url)
            return soup.find_all(class_="anime-r")[1].text
        except IndexError:
            raise ValueError

    @property
    async def _show_title(self) -> str:
        try:
            soup = await self.get_soup(self._show_url)
            return soup.find_all("h1")[0].text
        except IndexError:
            raise ValueError("Couldn'n find status of show: " + self._show_url)

    @property
    def _show_url(self) -> str:
        return self.feed.url.replace("yummyanime", "yummy-anime")
