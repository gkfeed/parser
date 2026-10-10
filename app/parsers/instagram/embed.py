import asyncio
import base64
import re
from datetime import timedelta
from io import BytesIO
from typing import override
from urllib.parse import urlparse

import structlog
from PIL import Image, ImageOps

from app.core.worker_kind import WorkerKind
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.exceptions import FeedUnavailable
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.result_size import ResultSizeExtension
from app.serializers.feed import Item
from app.services.hash import HashService
from app.services.http import HttpRequestError, HttpService
from app.services.instagram import InstagramService
from app.utils.datetime import constant_datetime

logger = structlog.get_logger(__name__)
_IMAGE_SOURCE = re.compile(r'src="data:[^;]+;base64,([^"]+)"')


class InstagramFeed(
    ItemsHashExtension, HttpParserExtension, CacheFeedExtension, ResultSizeExtension
):
    worker_kind = WorkerKind.HEAVY
    _cache_storage_time_if_success = timedelta(weeks=1)
    _max_download_bytes = 20 * 1024 * 1024
    _max_image_pixels = 20_000_000

    @override
    async def _generate_hash(self, item: Item) -> str:
        match = _IMAGE_SOURCE.search(item.text)
        if match:
            return HashService.hash_str(match.group(1))
        return HashService.hash_str(item.text)

    async def _parse_items(self) -> list[Item]:
        media = await InstagramService(self._user_name, self.cache).get_media()
        items: list[Item] = []
        for media_item in media:
            item = await self._create_image_item(media_item.url, media_item.post_url)
            items.append(item)
        return items

    async def _create_image_item(self, src: str, link: str) -> Item:
        try:
            response = await HttpService.get_response(
                src, max_bytes=self._max_download_bytes
            )
        except HttpRequestError as exc:
            raise FeedUnavailable(self.feed.url, "image_download_failed") from exc
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if response.status >= 400 or not content_type.startswith("image/"):
            logger.warning(
                "instagram_image_rejected",
                status=response.status,
                content_type=content_type,
                reason="invalid_response",
            )
            raise FeedUnavailable(self.feed.url, "invalid_image_response")
        try:
            mime_type = await asyncio.to_thread(self._validate_image, response.content)
        except (
            OSError,
            ValueError,
            Image.DecompressionBombError,
        ) as exc:
            logger.warning("instagram_image_rejected", reason="invalid_image")
            raise FeedUnavailable(self.feed.url, "invalid_image") from exc

        encoded = base64.b64encode(response.content).decode("utf-8")
        logger.info(
            "instagram_image_prepared",
            image_bytes=len(response.content),
        )
        img_tag = (
            f'<img src="data:{mime_type};base64,{encoded}" alt="{self._user_name}" />'
        )
        return Item(
            title="inst: " + self._user_name,
            text=f"{self._user_name}<br>{img_tag}",
            date=constant_datetime,
            link=link,
            hash=HashService.hash_str(encoded),
        )

    @override
    async def reduce_result_size(
        self, original_items: list[Item], attempt: int
    ) -> list[Item] | None:
        items: list[Item] = []
        for item in original_items:
            match = _IMAGE_SOURCE.search(item.text)
            if match is None:
                return None
            original = base64.b64decode(match.group(1), validate=True)
            compressed = await asyncio.to_thread(
                self._resize_image, original, len(original) // (2**attempt)
            )
            if len(compressed) >= len(original):
                items.append(item)
                continue
            encoded = base64.b64encode(compressed).decode("utf-8")
            replacement = f'src="data:image/jpeg;base64,{encoded}"'
            text = item.text[: match.start()] + replacement + item.text[match.end() :]
            # Re-encode the original each time and keep its deduplication hash.
            items.append(item.model_copy(update={"text": text}))
            logger.info(
                "instagram_image_compressed",
                attempt=attempt,
                original_bytes=len(original),
                image_bytes=len(compressed),
            )
        return items or None

    @classmethod
    def _validate_image(cls, data: bytes) -> str:
        with Image.open(BytesIO(data)) as image:
            if image.width * image.height > cls._max_image_pixels:
                raise ValueError("Image exceeds pixel limit")
            mime_type = Image.MIME.get(image.format or "")
            if mime_type is None:
                raise ValueError("Unknown image format")
            image.verify()
            return mime_type

    @classmethod
    def _resize_image(cls, data: bytes, budget: int) -> bytes:
        with Image.open(BytesIO(data)) as source:
            if source.width * source.height > cls._max_image_pixels:
                raise ValueError("Image exceeds pixel limit")
            image = ImageOps.exif_transpose(source).convert("RGB")
        while True:
            for quality in (85, 70, 55, 40):
                output = BytesIO()
                image.save(output, format="JPEG", quality=quality, optimize=True)
                content = output.getvalue()
                if len(content) <= budget or (max(image.size) <= 128 and quality == 40):
                    return content
            image.thumbnail(
                (max(128, image.width * 3 // 4), max(128, image.height * 3 // 4))
            )

    @property
    def _user_name(self) -> str:
        path = urlparse(self.feed.url).path.rstrip("/")
        return path.rsplit("/", 1)[-1].removeprefix("@")
