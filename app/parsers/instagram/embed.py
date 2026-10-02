import base64
import re
from datetime import timedelta
from typing import override
from urllib.parse import urlparse

from app.core.worker_kind import WorkerKind
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.serializers.feed import Item
from app.services.hash import HashService
from app.services.http import HttpRequestError
from app.services.instagram import InstagramService
from app.utils.datetime import constant_datetime
from app.utils.media import detect_mime_type
from app.workers.http import get_html


class InstagramFeed(ItemsHashExtension, HttpParserExtension, CacheFeedExtension):
    worker_kind = WorkerKind.HEAVY
    _cache_storage_time_if_success = timedelta(weeks=1)

    @override
    async def _generate_hash(self, item: Item) -> str:
        match = re.search(r'src="data:[^;]+;base64,([^"]+)"', item.text)
        if match:
            return HashService.hash_str(match.group(1))
        return HashService.hash_str(item.text)

    async def _parse_items(self) -> list[Item]:
        media = await InstagramService(self._user_name, self.cache).get_media()

        items: list[Item] = []
        for media_item in media:
            item = await self._create_image_item(media_item.url, media_item.post_url)
            if item:
                items.append(item)
        return items

    async def _create_image_item(self, src: str, link: str) -> Item | None:
        try:
            img_bytes = await get_html(src)
        except HttpRequestError:
            return None

        encoded = base64.b64encode(img_bytes).decode("utf-8")
        mime_type = detect_mime_type(img_bytes)
        img_tag = (
            f'<img src="data:{mime_type};base64,{encoded}" alt="{self._user_name}" />'
        )
        return Item(
            title="inst: " + self._user_name,
            text=f"{self._user_name}<br>{img_tag}",
            date=constant_datetime,
            link=link,
        )

    @property
    def _user_name(self) -> str:
        path = urlparse(self.feed.url).path.rstrip("/")
        return path.rsplit("/", 1)[-1].removeprefix("@")
