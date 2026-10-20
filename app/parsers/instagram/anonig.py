import asyncio
import re
from datetime import timedelta
from typing import override
from urllib.parse import urlparse

import structlog
from bs4.element import Tag

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.exceptions import FeedUnavailable
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.serializers.feed import Item
from app.services.anonyig import (
    ANONYIG_URL,
    AnonyigClient,
    AnonyigError,
    AnonyigOptions,
)
from app.services.hash import HashService
from app.services.http import HttpRequestError
from app.services.image import EmbeddedImage, ImageService
from app.utils.datetime import constant_datetime

logger = structlog.get_logger(__name__)


class InstagramFeed(ItemsHashExtension, SeleniumParserExtension, CacheFeedExtension):
    _http_response_storage_time = timedelta(seconds=0)  # url is similar
    _cache_storage_time_if_success = timedelta(weeks=1)
    _image_download_concurrency = 6
    _max_media_items = 30
    _service_url = ANONYIG_URL

    @override
    async def _generate_hash(self, item: Item) -> str:
        video_match = re.search(r'<video[^>]+src="([^"]+)"', item.text)
        if video_match:
            return HashService.hash_str(video_match.group(1))

        match = re.search(r'src="data:[^;]+;base64,([^"]+)"', item.text)
        if match:
            return HashService.hash_str(match.group(1))
        return HashService.hash_str(item.text)

    async def _parse_items(self) -> list[Item]:
        soup = await self.get_soup(self._service_url)
        media = soup.select(".search-result .profile-media-list__item")[
            : self._max_media_items
        ]
        semaphore = asyncio.Semaphore(self._image_download_concurrency)

        async def create_item(item: Tag) -> Item | None:
            async with semaphore:
                return await self._create_item_from_media(item)

        items = await asyncio.gather(*(create_item(item) for item in media))
        # Only explicitly unsupported videos may be omitted.
        return [item for item in items if item is not None]

    async def _create_item_from_media(self, media: Tag) -> Item | None:
        if media.find(class_="tags__item--video") is not None:
            # Video links expire. Skip every explicitly marked video, including
            # links without an .mp4 suffix, rather than publishing its thumbnail.
            logger.info("anonyig_media_skipped", reason="unsupported_video")
            return None

        img = media.select_one("img")
        if img is None:
            raise ValueError("Anonyig media is missing an image")

        src = img.get("src")
        if not isinstance(src, str) or not src.strip():
            raise ValueError("Anonyig image is missing a valid src")
        src = src.strip()

        image_url = await self._embedded_image_url(src)
        img_tag = f'<img src="{image_url}" alt="{self._user_name}" />'

        return Item(
            title="inst: " + self._user_name,
            text=f"{self._user_name}<br>{img_tag}",
            date=constant_datetime,
            link=self.feed.url,
        )

    async def _embedded_image_url(self, src: str) -> str:
        if src.startswith("data:"):
            header, separator, encoded = src.partition(",")
            if not separator or not re.fullmatch(
                r"data:image/[a-zA-Z0-9.+-]+;base64", header
            ):
                raise ValueError("Anonyig image has an invalid base64 data URI header")
            original = EmbeddedImage.from_base64(header[5:-7], encoded)
            image = await ImageService.from_content(original.content)
            if original.mime_type.lower() != image.mime_type:
                raise ValueError("Anonyig image MIME type does not match its data")
            # Keep the source's base64 spelling, which is also the item identity.
            return f"data:{image.mime_type};base64,{encoded}"

        parsed = urlparse(src)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("Anonyig image has an invalid URL")
        try:
            image = await ImageService.download(src)
        except HttpRequestError as exc:
            raise FeedUnavailable(self.feed.url, "image_download_failed") from exc
        return image.data_url

    @property
    def _anonyig(self) -> AnonyigClient:
        return AnonyigClient(
            username=self._user_name,
            media_kind="posts",
            options=AnonyigOptions(
                pagination_settle_seconds=5, max_media_items=self._max_media_items
            ),
        )

    @override
    async def _fetch_html(self, url: str) -> bytes:
        try:
            return await self._anonyig.get_html(url)
        except AnonyigError as exc:
            reason = exc.reason
            if reason in ("page_timeout", "browser_error"):
                reason = "browser_action_failed"
            raise FeedUnavailable(self.feed.url, reason) from exc

    @override
    def _validate_html(self, url: str, html: bytes) -> None:
        try:
            self._anonyig.validate_html(html)
        except AnonyigError as exc:
            raise FeedUnavailable(self.feed.url, exc.reason) from exc

    @property
    def _user_name(self) -> str:
        path = urlparse(self.feed.url).path.rstrip("/")
        return path.rsplit("/", 1)[-1].removeprefix("@")
