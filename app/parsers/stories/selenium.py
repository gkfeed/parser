import asyncio
from datetime import timedelta
from typing import override
from urllib.parse import urlsplit

import structlog
from bs4 import Tag
from requests.exceptions import RequestException
from selenium.webdriver.remote.webdriver import WebDriver

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.exceptions import FeedUnavailable
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.serializers.feed import Item
from app.services.hash import HashService
from app.services.media_upload import FallbackUploader
from app.utils.datetime import constant_datetime
from app.utils.logging import url_log_fields

from .errors import unavailable
from .page import StoriesPage

logger = structlog.get_logger(__name__)


class InstagramStoriesFeed(
    ItemsHashExtension, SeleniumParserExtension, CacheFeedExtension
):
    _http_response_storage_time = timedelta(seconds=0)  # url is similar
    success_result_delay = timedelta(days=1)
    _selenium_wait_time = 10
    _page_load_timeout_seconds = 30
    _should_delete_cookies = True
    _service_url = "https://anonyig.com/en/iganony/"
    # This ad player creates/detaches nested frames that can hang ChromeDriver.
    _blocked_url_patterns = ("*://player.avplayer.com/*",)

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

    @override
    def make_actions(self, driver: WebDriver) -> None:
        StoriesPage(driver, self.feed.url).run()

    def _unavailable(self, reason: str) -> FeedUnavailable:
        return unavailable(self.feed.url, reason)

    @property
    def _user_name(self) -> str:
        return self.feed.url.split("/")[-1]
