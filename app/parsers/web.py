from typing import override

from app.core.worker_kind import WorkerKind
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.serializers.feed import Item
from app.services.hash import HashService
from app.services.rss import RSSParser

# The retired TWiN domain redirects to unrelated HTML. Use the newsletter's
# published RSS endpoint for subscriptions that still contain the old URL.
_FEED_URL_REPLACEMENTS = {
    "https://this-week-in-neovim.org/rss": (
        "https://dotfyle.com/this-week-in-neovim/rss.xml"
    ),
}


class WebFeed(ItemsHashExtension, HttpParserExtension):
    worker_kind = WorkerKind.LIGHT

    @override
    async def _generate_hash(self, item: Item) -> str:
        if item.guid:
            return HashService.hash_str(item.guid)
        return HashService.hash_str(item.title + item.text)

    async def _parse_items(self) -> list[Item]:
        url = _FEED_URL_REPLACEMENTS.get(self.feed.url, self.feed.url)
        return await RSSParser.parse_items(url)
