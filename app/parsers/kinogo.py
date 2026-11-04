from datetime import timedelta
from typing import override

from app.core.worker_kind import WorkerKind
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.serializers.feed import Item
from app.utils.datetime import constant_datetime
from app.utils.html import require_tag, required_text


class KinogoFeed(ItemsHashExtension, HttpParserExtension, CacheFeedExtension):
    worker_kind = WorkerKind.LIGHT
    _cache_storage_time = timedelta(hours=1)

    @override
    async def _parse_items(self) -> list[Item]:
        soup = await self.get_soup(self.feed.url)
        title_tag = require_tag(soup.find("h1"), "Kinogo show title")
        title = required_text(title_tag, "Kinogo show title", separator=" ")

        status_tag = require_tag(soup.find(class_="status7"), "Kinogo show status")
        status = required_text(status_tag, "Kinogo show status", separator=" ")

        return [
            Item(
                title=f"{title} {status}",
                text=status,
                date=constant_datetime,
                link=self.feed.url,
            )
        ]
