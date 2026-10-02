from bs4 import Tag

from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.serializers.feed import Item
from app.utils.datetime import constant_datetime


class RezkaCollectionFeed(ItemsHashExtension, SeleniumParserExtension):
    _base_url = "https://hdrezka.me"
    _max_items = 30
    _selenium_wait_time = 5

    async def _parse_items(self) -> list[Item]:
        soup = await self.get_soup(self.feed.url)
        titles = self._extract_collection_titles(soup)

        return [
            self._item_from_title(title)
            for title in titles
        ]

    def _item_from_title(self, title_tag: Tag) -> Item:
        anchor = title_tag.find("a")
        if not isinstance(anchor, Tag) or "href" not in anchor.attrs:
            raise ValueError(
                "Could not extract collection item: <a> tag or href attribute not found."
            )
        return Item(
            title=anchor.text,
            link=self._normalize_href(str(anchor["href"])),
            text=anchor.text,
            date=constant_datetime,
        )

    def _extract_collection_titles(self, soup: Tag) -> list[Tag]:
        titles = [
            t
            for t in soup.find_all(class_="b-content__inline_item-link")
            if isinstance(t, Tag)
        ][: self._max_items]
        if not titles:
            raise ValueError("Could not extract collection titles: no titles found.")
        return titles

    def _normalize_href(self, href: str) -> str:
        return self._base_url + href if href.startswith("/") else href
