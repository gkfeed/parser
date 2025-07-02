from datetime import timedelta, datetime


from bs4.element import Tag

from app.utils.datetime import convert_datetime, constant_datetime
from app.serializers.feed import Item
from app.extensions.parsers.http import HttpParserExtension


class ShikiFeed(HttpParserExtension):
    _cache_storage_time = timedelta(hours=1)
    _cache_storage_time_if_success = timedelta(days=1)

    @property
    async def items(self) -> list[Item]:
        soup = await self.get_soup(self.feed.url)

        title = await self._show_title
        menu_links = soup.find_all(class_="b-menu-links")

        news = []
        if menu_links:
            menu_link = menu_links[0]
            if isinstance(menu_link, Tag):
                news = [
                    n
                    for n in menu_link.find_all(class_="entry")
                    if isinstance(n, Tag)
                ]

        return [
            Item(
                title=title + " " + self._get_item_status(item),
                text=self._get_item_status(item),
                date=self._get_item_date(item),
                link=self.feed.url,
            )
            for item in news
            if isinstance(item, Tag)
        ]

    @property
    async def _show_title(self) -> str:
        try:
            soup = await self.get_soup(self.feed.url)
            h1 = soup.find("h1")
            if isinstance(h1, Tag):
                return h1.text
            raise ValueError
        except IndexError:
            raise ValueError

    def _get_item_status(self, item: Tag) -> str:
        span_tag = item.find("span")
        if isinstance(span_tag, Tag):
            return span_tag.text
        raise ValueError

    def _get_item_date(self, item: Tag) -> datetime:
        span_tag = item.find("span")
        if isinstance(span_tag, Tag):
            time_tag = span_tag.find("time")
            if isinstance(time_tag, Tag):
                datetime_str = time_tag.get("datetime")
                if isinstance(datetime_str, str):
                    return convert_datetime(datetime_str)
        return constant_datetime
