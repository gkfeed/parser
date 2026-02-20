from datetime import timedelta, datetime


from bs4.element import Tag

from app.utils.datetime import convert_datetime, constant_datetime
from app.serializers.feed import Item
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.hash import ItemsHashExtension


class ShikiFeed(ItemsHashExtension, HttpParserExtension):
    _cache_storage_time = timedelta(hours=1)
    _cache_storage_time_if_success = timedelta(days=1)

    @property
    async def items(self) -> list[Item]:
        soup = await self.get_soup(self._url)

        title = await self._show_title
        menu_links = soup.find_all(class_="b-menu-links")

        if not menu_links:
            raise ValueError("No elements with class 'b-menu-links' found.")

        menu_link = menu_links[0]
        if not isinstance(menu_link, Tag):
            raise ValueError(
                "The first element with class 'b-menu-links' is not a Tag instance."
            )

        news = [n for n in menu_link.find_all(class_="entry") if isinstance(n, Tag)]

        return [
            Item(
                title=title + " " + self._get_item_status(item),
                text=self._get_item_status(item),
                date=self._get_item_date(item),
                link=self._url,
            )
            for item in reversed(news)
            if isinstance(item, Tag)
        ]

    @property
    async def _show_title(self) -> str:
        soup = await self.get_soup(self._url)
        h1 = soup.find("h1")

        if not isinstance(h1, Tag):
            raise ValueError("h1 tag not found or not a Tag instance.")

        return h1.text

    @property
    def _url(self) -> str:
        return self.feed.url.replace("shikimori.me", "shikimori.one")

    def _get_item_status(self, item: Tag) -> str:
        span_tag = item.find_all("span")[-1]
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
