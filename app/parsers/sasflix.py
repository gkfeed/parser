from typing import override

from app.extensions.parsers.hash import ItemLinkHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.serializers.feed import Item
from app.services.rss import RSSParser


class SasflixFeed(ItemLinkHashExtension, HttpParserExtension):
    @override
    async def _fetch_html(self, url: str) -> bytes:
        return await RSSParser.fetch_bytes(url, headers=self._headers)

    async def _parse_items(self) -> list[Item]:
        rss_url = f"{self.feed.url.rstrip('/').removesuffix('/rss.xml')}/rss.xml"

        content = await self.get_html(rss_url)
        feed = RSSParser.parse_bytes(
            content,
            content_priority=("encoded", "enclosure", "description"),
            default_title="No Title",
        )
        return RSSParser.items_from_feed(feed, include_guid=False)
