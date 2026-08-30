from bs4 import Tag

from app.extensions.parsers.selenium import SeleniumParserExtension
from app.serializers.feed import Item
from app.utils.datetime import constant_datetime


class RezkaCollectionFeed(SeleniumParserExtension):
    _base_url = "https://hdrezka.me"
    _max_items = 30
    _selenium_wait_time = 5

    @property
    async def items(self) -> list[Item]:
        soup = await self.get_soup(self.feed.url)
        titles = self._extract_collection_titles(soup)

        return [
            Item(
                title=self._extract_item_title(title),
                link=self._extract_item_link(title),
                text=self._extract_item_text(title),
                date=constant_datetime,
            )
            for title in titles
        ]

    def _extract_item_title(self, title_tag: Tag) -> str:
        anchor = title_tag.find("a")
        if not (anchor and isinstance(anchor, Tag)):
            raise ValueError(
                "Could not extract item title: <a> tag not found or not a Tag instance."
            )
        return anchor.text

    def _extract_item_text(self, title_tag: Tag) -> str:
        anchor = title_tag.find("a")
        if not (anchor and isinstance(anchor, Tag)):
            raise ValueError(
                "Could not extract item text: <a> tag not found or not a Tag instance."
            )
        return anchor.text

    def _extract_collection_titles(self, soup: Tag) -> list[Tag]:
        titles = [
            t
            for t in soup.find_all(class_="b-content__inline_item-link")
            if isinstance(t, Tag)
        ][: self._max_items]
        if not titles:
            raise ValueError("Could not extract collection titles: no titles found.")
        return titles

    def _extract_item_link(self, title_tag: Tag) -> str:
        anchor = title_tag.find("a")
        if not isinstance(anchor, Tag) or "href" not in anchor.attrs:
            raise ValueError(
                "Could not extract item link: <a> tag or href attribute not found."
            )
        return self._normalize_href(str(anchor["href"]))

    def _normalize_href(self, href: str) -> str:
        return self._base_url + href if href.startswith("/") else href
