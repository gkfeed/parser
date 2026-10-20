import asyncio
from datetime import UTC, datetime, timedelta
from typing import override
from urllib.parse import urlsplit

import structlog
from bs4 import Tag
from requests.exceptions import RequestException

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
from app.services.media_upload import FallbackUploader
from app.utils.datetime import constant_datetime
from app.utils.logging import url_log_fields

logger = structlog.get_logger(__name__)


class InstagramStoriesFeed(
    ItemsHashExtension, SeleniumParserExtension, CacheFeedExtension
):
    _http_response_storage_time = timedelta(seconds=0)  # url is similar
    _cache_storage_time_if_success = timedelta(days=1)
    _service_url = ANONYIG_URL

    @override
    async def _generate_hash(self, item: Item) -> str:
        try:
            return await HashService.hash_video_from_url(item.link)
        except RequestException as exc:
            logger.warning(
                "stories_media_hash_failed",
                error_type=type(exc).__name__,
                **url_log_fields(item.link),
            )
            raise self._unavailable("media_hash_error") from exc

    async def _parse_items(self) -> list[Item]:
        soup = await self.get_soup(self._service_url)
        uploads = await asyncio.gather(
            *(
                FallbackUploader.upload_with_url(link)
                for link in self._extract_media_links(soup)
            )
        )
        links = [link for link in uploads if link is not None]
        logger.info("stories_media_processed", found=len(uploads), uploaded=len(links))
        if len(links) != len(uploads):
            raise self._unavailable("media_upload_error")

        return [
            Item(
                title="inst: " + self._user_name,
                text=self._user_name,
                date=constant_datetime,
                link=link,
            )
            for link in links
        ]

    def _extract_media_links(self, soup: Tag) -> list[str]:
        active_tab = soup.select_one(".search-result .tabs-component__button--active")
        if not isinstance(active_tab, Tag):
            raise self._unavailable("media_response_invalid")
        if active_tab.get_text(strip=True).lower() != "stories":
            raise self._unavailable("media_response_invalid")

        media = soup.select(".search-result .profile-media-list__item")
        if not media:
            raise self._unavailable("empty_unverified")
        return [self._media_link(card) for card in media]

    def _media_link(self, media: Tag) -> str:
        download = media.select_one("a.download-btn[href]")
        if not isinstance(download, Tag):
            raise self._unavailable("media_response_invalid")
        href = download.get("href")
        if not isinstance(href, str):
            raise self._unavailable("media_response_invalid")
        try:
            url = urlsplit(href)
        except ValueError as exc:
            raise self._unavailable("media_response_invalid") from exc
        if url.scheme not in ("http", "https") or not url.netloc:
            raise self._unavailable("media_response_invalid")
        return href

    @property
    def _anonyig(self) -> AnonyigClient:
        return AnonyigClient(
            username=self._user_name,
            media_kind="stories",
            options=AnonyigOptions(selenium_wait_seconds=10),
        )

    @override
    async def _fetch_html(self, url: str) -> bytes:
        try:
            return await self._anonyig.get_html(url)
        except AnonyigError as exc:
            raise self._unavailable(exc.reason) from exc

    @override
    def _validate_html(self, url: str, html: bytes) -> None:
        try:
            self._anonyig.validate_html(html)
        except AnonyigError as exc:
            raise self._unavailable(exc.reason) from exc

    def _unavailable(self, reason: str) -> FeedUnavailable:
        delay = (
            timedelta(days=1)
            if reason in ("private", "not_found")
            else timedelta(minutes=1)
        )
        return FeedUnavailable(self.feed.url, reason, datetime.now(UTC) + delay)

    @property
    def _user_name(self) -> str:
        return self.feed.url.split("/")[-1]
