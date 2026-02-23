from bs4 import BeautifulSoup, Tag
from typing import override

from app.serializers.feed import Item
from app.utils.datetime import convert_datetime
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.hash import ItemsHashExtension
from app.services.hash import HashService


class SasflixFeed(ItemsHashExtension, HttpParserExtension):
    @override
    async def _generate_hash(self, item: Item) -> str:
        return HashService.hash_str(item.link)

    @property
    async def items(self) -> list[Item]:
        rss_url = self.feed.url.rstrip("/")
        if not rss_url.endswith("/rss.xml"):
            rss_url += "/rss.xml"

        html = await self.get_html(rss_url)
        soup = BeautifulSoup(html, "xml")

        items = []
        for item_tag in soup.find_all("item"):
            if not isinstance(item_tag, Tag):
                continue

            title = getattr(item_tag.find("title"), "text", "No Title")
            link = getattr(item_tag.find("link"), "text", "")
            pub_date = getattr(item_tag.find("pubDate"), "text", "")

            content_encoded = item_tag.find(
                "encoded"
            )  # BeautifulSoup with 'xml' parser often maps 'content:encoded' to 'encoded'
            if not content_encoded:
                content_encoded = item_tag.find("content:encoded")

            description = content_encoded.text if content_encoded else ""

            if not description:
                enclosure = item_tag.find("enclosure")
                if isinstance(enclosure, Tag) and "url" in enclosure.attrs:
                    description = f'<img src="{enclosure["url"]}" alt="" />'

            items.append(
                Item(
                    title=title,
                    text=description,
                    link=link,
                    date=convert_datetime(pub_date),
                )
            )
        return items
