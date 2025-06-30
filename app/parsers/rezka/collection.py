from app.serializers.feed import Item
from app.utils.datetime import constant_datetime
from app.extensions.parsers.selenium import SeleniumParserExtension


class RezkaCollectionFeed(SeleniumParserExtension):
    _base_url = "https://hdrezka.me"
    _max_items = 5

    @property
    async def items(self) -> list[Item]:
        soup = await self.get_soup(self.feed.url)
        titles = soup.find_all(class_="b-content__inline_item-link")[: self._max_items]

        return [
            Item(
                title=title.a.text,
                link=self._normalize_href(title.a["href"]),
                text=title.a.text,
                date=constant_datetime,
            )
            for title in titles
        ]

    def _normalize_href(self, href: str) -> str:
        if href.startswith("/"):
            return self._base_url + href
        return href
