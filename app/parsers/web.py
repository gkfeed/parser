from rss_parser import Parser  # type: ignore
from rss_parser.models import FeedItem  # type: ignore

from app.utils.item_converter import convert_item
from app.serializers.feed import Item
from app.extentions.parsers.http import HttpParserExtention


class WebFeed(HttpParserExtention):
    @property
    async def items(self) -> list[Item]:
        return await self._get_items_from_web(self.feed.url)

    async def _get_items_from_web(self, url: str) -> list[Item]:
        return [convert_item(item) for item in await self.__get_feed_from_url(url)]

    async def __get_feed_from_url(self, url: str) -> list[FeedItem]:
        try:
            html = await self.get_html(url)
            return Parser(html).parse().feed
        except Exception as e:  # FIXME: Parser error
            raise ValueError
