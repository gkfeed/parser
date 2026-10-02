from typing import override

from app.core.worker_kind import WorkerKind
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.serializers.feed import Item
from app.services.hash import HashService
from app.services.rss import RSSParser


class WebFeed(ItemsHashExtension, HttpParserExtension):
    worker_kind = WorkerKind.LIGHT

    @override
    async def _generate_hash(self, item: Item) -> str:
        if item.guid:
            return HashService.hash_str(item.guid)
        return HashService.hash_str(item.title + item.text)

    async def _parse_items(self) -> list[Item]:
        return await RSSParser.parse_items(self.feed.url)
