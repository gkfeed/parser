from typing import override

from app.utils.datetime import convert_datetime
from app.serializers.feed import Item
from app.services.hash import HashService
from app.services.rss import RSSParser
from app.extentions.parsers.http import HttpParserExtention
from app.extentions.parsers.hash import ItemsHashExtension


class WebFeed(ItemsHashExtension, HttpParserExtention):
    @override
    async def _generate_hash(self, item: Item) -> str:
        if item.guid:
            print(item.guid)
            return HashService.hash_str(item.guid)
        return HashService.hash_str(item.title + item.text)

    @property
    async def items(self) -> list[Item]:
        return await self._get_items_from_web(self.feed.url)

    async def _get_items_from_web(self, url: str) -> list[Item]:
        return [self._convert_item(item) for item in await RSSParser.parse_feed(url)]

    def _convert_item(self, item_data: dict) -> Item:
        return Item(
            title=item_data.get("title", ""),
            link=item_data.get("link", ""),
            text=item_data.get("description", ""),
            date=convert_datetime(item_data.get("pub_date", "")),
            guid=item_data.get("guid", ""),
        )
