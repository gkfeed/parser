from typing import override

from bs4 import BeautifulSoup, Tag

from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.serializers.feed import Item
from app.services.hash import HashService
from app.utils.datetime import convert_datetime


def _extract_description(item_tag: Tag) -> str:
    # The XML parser often maps content:encoded to encoded.
    content_encoded = item_tag.find("encoded") or item_tag.find("content:encoded")
    description = content_encoded.text if content_encoded else ""
    if description:
        return description

    enclosure = item_tag.find("enclosure")
    if isinstance(enclosure, Tag) and "url" in enclosure.attrs:
        return f'<img src="{enclosure["url"]}" alt="" />'

    return ""


class SasflixFeed(ItemsHashExtension, HttpParserExtension):
    @override
    async def _generate_hash(self, item: Item) -> str:
        return HashService.hash_str(item.link)

    async def _parse_items(self) -> list[Item]:
        rss_url = f"{self.feed.url.rstrip('/').removesuffix('/rss.xml')}/rss.xml"

        html = await self.get_html(rss_url)
        soup = BeautifulSoup(html, "xml")

        items = []
        for item_tag in soup.find_all("item"):
            if not isinstance(item_tag, Tag):
                continue

            title = getattr(item_tag.find("title"), "text", "No Title")
            link = getattr(item_tag.find("link"), "text", "")
            pub_date = getattr(item_tag.find("pubDate"), "text", "")

            items.append(
                Item(
                    title=title,
                    text=_extract_description(item_tag),
                    link=link,
                    date=convert_datetime(pub_date),
                )
            )
        return items
