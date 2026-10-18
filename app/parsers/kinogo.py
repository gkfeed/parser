from datetime import timedelta
from typing import override

from bs4 import Tag

from app.core.worker_kind import WorkerKind
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.serializers.feed import Item
from app.utils.datetime import constant_datetime


class KinogoFeed(ItemsHashExtension, HttpParserExtension, CacheFeedExtension):
    worker_kind = WorkerKind.LIGHT
    _cache_storage_time = timedelta(hours=1)

    @override
    async def _parse_items(self) -> list[Item]:
        soup = await self.get_soup(self.feed.url)
        title_tag = soup.find("h1")
        if not isinstance(title_tag, Tag):
            raise ValueError(  # noqa: TRY004 - missing page data is a value error
                "Couldn'n find status of show: " + self.feed.url
            )
        title = title_tag.text

        status_tag = soup.find(class_="status7")
        if not isinstance(status_tag, Tag):
            raise ValueError  # noqa: TRY004 - missing page data is a value error
        status = status_tag.text

        return [
            Item(
                title=f"{title} {status}",
                text=status,
                date=constant_datetime,
                link=self.feed.url,
            )
        ]
