import re
from datetime import timedelta
from typing import override
from urllib.parse import urlparse

import structlog

from app.core.worker_kind import WorkerKind
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.exceptions import FeedUnavailable
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.result_size import ResultSizeExtension
from app.serializers.feed import Item
from app.services.hash import HashService
from app.services.http import HttpRequestError
from app.services.image import EmbeddedImage, ImageResponseError, ImageService
from app.services.instagram import InstagramService
from app.utils.datetime import constant_datetime

logger = structlog.get_logger(__name__)
_IMAGE_SOURCE = re.compile(r'src="data:(?P<mime_type>[^;]+);base64,(?P<encoded>[^"]+)"')


class InstagramFeed(
    ItemsHashExtension, HttpParserExtension, CacheFeedExtension, ResultSizeExtension
):
    worker_kind = WorkerKind.HEAVY
    _cache_storage_time_if_success = timedelta(weeks=1)
    # At most 30 images are embedded, so base64 stays near 40 MiB before JSON.
    _max_image_bytes = 1024 * 1024

    @override
    async def _generate_hash(self, item: Item) -> str:
        match = _IMAGE_SOURCE.search(item.text)
        if match:
            return HashService.hash_str(match["encoded"])
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
            original = await ImageService.download(src)
            image = original
            if len(original.content) > self._max_image_bytes:
                image = await ImageService.resize(original, self._max_image_bytes)
        except ImageResponseError as exc:
            logger.warning(
                "instagram_image_rejected",
                status=exc.status,
                content_type=exc.content_type,
                reason="invalid_response",
            )
            raise FeedUnavailable(self.feed.url, "invalid_image_response") from exc
        except HttpRequestError as exc:
            raise FeedUnavailable(self.feed.url, "image_download_failed") from exc
        except ValueError as exc:
            logger.warning("instagram_image_rejected", reason="invalid_image")
            raise ValueError(
                f"Invalid Instagram image for {self.feed.url}: {exc}"
            ) from exc

        logger.info(
            "instagram_image_prepared",
            original_bytes=len(original.content),
            image_bytes=len(image.content),
        )
        img_tag = f'<img src="{image.data_url}" alt="{self._user_name}" />'
        return Item(
            title="inst: " + self._user_name,
            text=f"{self._user_name}<br>{img_tag}",
            date=constant_datetime,
            link=link,
            # Keep existing item identities when their embedded image is resized.
            hash=HashService.hash_str(original.encoded),
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
            try:
                original = EmbeddedImage.from_base64(
                    match["mime_type"], match["encoded"]
                )
                compressed = await ImageService.resize(
                    original, len(original.content) // (2**attempt)
                )
            except ValueError as exc:
                raise ValueError(
                    f"Cannot reduce Instagram image for {self.feed.url}: {exc}"
                ) from exc
            if len(compressed.content) >= len(original.content):
                items.append(item)
                continue
            replacement = f'src="{compressed.data_url}"'
            text = item.text[: match.start()] + replacement + item.text[match.end() :]
            # Re-encode the original each time and keep its deduplication hash.
            items.append(item.model_copy(update={"text": text}))
            logger.info(
                "instagram_image_compressed",
                attempt=attempt,
                original_bytes=len(original.content),
                image_bytes=len(compressed.content),
            )
        return items or None

    @property
    def _user_name(self) -> str:
        path = urlparse(self.feed.url).path.rstrip("/")
        return path.rsplit("/", 1)[-1].removeprefix("@")
