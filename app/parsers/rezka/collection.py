from bs4 import Tag
from app.serializers.feed import Item
from app.utils.datetime import constant_datetime
from app.extensions.parsers.selenium import SeleniumParserExtension


class RezkaCollectionFeed(SeleniumParserExtension):
    _base_url = "https://hdrezka.me"
    _max_items = 5

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
        if not (title_tag.a and isinstance(title_tag.a, Tag)):
            raise ValueError(
                "Could not extract item title: <a> tag not found or not a Tag instance."
            )
        return title_tag.a.text

    def _extract_item_text(self, title_tag: Tag) -> str:
        if not (title_tag.a and isinstance(title_tag.a, Tag)):
            raise ValueError(
                "Could not extract item text: <a> tag not found or not a Tag instance."
            )
        return title_tag.a.text

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
        if not (title_tag.a and "href" in title_tag.a.attrs):
            raise ValueError(
                "Could not extract item link: <a> tag or href attribute not found."
            )
        return self._normalize_href(str(title_tag.a["href"]))

    def _normalize_href(self, href: str) -> str:
        if href.startswith("/"):
            return self._base_url + href
        return href
