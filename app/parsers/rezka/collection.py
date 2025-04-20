from app.serializers.feed import Item
from app.utils.datetime import constant_datetime
from app.extentions.parsers.selenium import SeleniumParserExtention


class RezkaCollecionFeed(SeleniumParserExtention):
    _max_items = 5

    @property
    async def items(self) -> list[Item]:
        collection_url = self.feed.url + "/?filter=last"
        soup = await self.get_soup(collection_url)
        titles = soup.find_all(class_="b-content__inline_item-link")[: self._max_items]

        return [
            Item(
                title=title.a.text,
                link=title.a["href"],
                text=title.a.text,
                date=constant_datetime,
            )
            for title in titles
        ]
