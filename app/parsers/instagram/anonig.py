import asyncio
import base64
import binascii
import re
from datetime import timedelta
from io import BytesIO
from typing import override
from urllib.parse import urlparse

import structlog
from bs4.element import Tag
from PIL import Image
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.exceptions import FeedUnavailable
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.serializers.feed import Item
from app.services.hash import HashService
from app.services.http import HttpRequestError, HttpService
from app.utils.datetime import constant_datetime
from app.utils.media import detect_mime_type

logger = structlog.get_logger(__name__)


class InstagramFeed(ItemsHashExtension, SeleniumParserExtension, CacheFeedExtension):
    _http_response_storage_time = timedelta(seconds=0)  # url is similar
    _cache_storage_time_if_success = timedelta(weeks=1)
    _selenium_wait_time = 0
    _results_wait_time = 30
    _load_more_wait_time = 5
    _max_media_items = 30
    _image_download_concurrency = 6
    _page_load_timeout_seconds = 30
    _should_delete_cookies = True
    _service_url = "https://anonyig.com/en/iganony/"

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

        media_list_items = soup.find_all(class_="profile-media-list__item")
        if not media_list_items:
            error = soup.select_one(".error-message__text") or soup.select_one(
                ".error-message"
            )
            if isinstance(error, Tag):
                self._check_error(error.get_text(" ", strip=True))
                return []
            raise ValueError("Anonyig response has no media or explicit empty result")

        media = [item for item in media_list_items if isinstance(item, Tag)]
        semaphore = asyncio.Semaphore(self._image_download_concurrency)

        async def create_item(item: Tag) -> Item | None:
            async with semaphore:
                return await self._create_item_from_media(item)

        items = await asyncio.gather(*(create_item(item) for item in media))
        return [item for item in items if item is not None]

    async def _create_item_from_media(self, media: Tag) -> Item | None:
        is_video = media.find(class_="tags__item--video") is not None

        link_tag = media.find("a")
        media_url = link_tag.get("href") if isinstance(link_tag, Tag) else None

        if is_video and isinstance(media_url, str) and ".mp4" in media_url:
            # Video links expire, so keep the existing explicit skip policy.
            logger.info("anonyig_media_skipped", reason="unsupported_video")
            return None

        img = media.select_one("img")
        if img is None:
            raise ValueError("Anonyig media is missing an image")

        src = img.get("src")
        if isinstance(src, list):
            src = src[0] if src else None

        if not isinstance(src, str) or not src.strip():
            raise ValueError("Anonyig image is missing src")

        if src.startswith("data:"):
            header, separator, encoded = src.partition(",")
            if not separator or not re.fullmatch(
                r"data:image/[a-zA-Z0-9.+-]+;base64", header
            ):
                raise ValueError("Anonyig image has an invalid base64 data URI header")
            mime_type = header[5:-7]
            try:
                img_bytes = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error):
                raise ValueError(
                    "Anonyig image data URI contains invalid base64"
                ) from None
        else:
            try:
                response = await HttpService.get_response(src)
            except HttpRequestError:
                logger.warning(
                    "anonyig_media_unavailable", reason="image_download_failed"
                )
                raise FeedUnavailable(self.feed.url, "image_download_failed") from None
            if response.status >= 400:
                logger.warning(
                    "anonyig_media_unavailable",
                    reason="image_download_failed",
                    status=response.status,
                )
                raise FeedUnavailable(self.feed.url, "image_download_failed")
            img_bytes = response.content
            encoded = base64.b64encode(img_bytes).decode("utf-8")
            mime_type = detect_mime_type(img_bytes)

        try:
            with Image.open(BytesIO(img_bytes)) as image:
                image.verify()
        except (OSError, ValueError, Image.DecompressionBombError):
            raise ValueError("Anonyig image contains invalid image data") from None

        img_tag = (
            f'<img src="data:{mime_type};base64,{encoded}" alt="{self._user_name}" />'
        )

        return Item(
            title="inst: " + self._user_name,
            text=f"{self._user_name}<br>{img_tag}",
            date=constant_datetime,
            link=self.feed.url,
        )

    @override
    def make_actions(self, driver: WebDriver):
        try:
            reject_consent = driver.find_element(
                By.CSS_SELECTOR, ".fc-cta-do-not-consent"
            )
            self._click(driver, reject_consent)
        except NoSuchElementException:
            pass

        # Insert account name in form
        link = driver.find_element(
            By.CSS_SELECTOR, "form.search-form input.search-form__input"
        )
        link.send_keys(self._user_name)

        # Click search button
        button = driver.find_element(
            By.CSS_SELECTOR,
            ".search-form__button",
        )
        self._click(driver, button)

        result = WebDriverWait(driver, self._results_wait_time).until(
            expected_conditions.any_of(
                expected_conditions.presence_of_element_located(
                    (By.CSS_SELECTOR, ".profile-media-list__item")
                ),
                expected_conditions.presence_of_element_located(
                    (By.CSS_SELECTOR, ".error-message")
                ),
            )
        )
        if "error-message" in (result.get_attribute("class") or "").split():
            errors = result.find_elements(By.CSS_SELECTOR, ".error-message__text")
            error = errors[0] if errors else result
            self._check_error(error.get_attribute("textContent") or "")
            return

        search_result = driver.find_element(By.CSS_SELECTOR, ".search-result")
        if not search_result.is_displayed():
            # The landing-page experiment hides the populated result in headless
            # browsers, preventing its load-more IntersectionObserver from firing.
            driver.execute_script(
                "arguments[0].style.setProperty('display', 'block', 'important');"
                "arguments[0].style.setProperty('visibility', 'visible', 'important');",
                search_result,
            )

        self._load_more_media(driver)

    def _check_error(self, message: str) -> None:
        message = " ".join(message.lower().split())
        # Only an explicit empty-posts message confirms a successful empty feed.
        if message.rstrip(".! ") in (
            "no posts",
            "no posts found",
            "no publications found",
        ):
            logger.info("anonyig_posts_empty")
            return
        reason = "upstream_error"
        if "private" in message:
            reason = "private"
        elif any(
            text in message
            for text in ("user not found", "profile not found", "account not found")
        ):
            reason = "not_found"
        logger.warning("anonyig_source_unavailable", reason=reason)
        raise FeedUnavailable(self.feed.url, reason)

    def _load_more_media(self, driver: WebDriver) -> None:
        media_selector = ".profile-media-list__item"
        trigger_selector = ".profile-media-list > .trigger"
        media_count = len(driver.find_elements(By.CSS_SELECTOR, media_selector))

        while media_count < self._max_media_items:
            try:
                trigger = driver.find_element(By.CSS_SELECTOR, trigger_selector)
            except NoSuchElementException:
                break

            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", trigger
            )

            def media_count_increased(
                current_driver: WebDriver, previous_count: int = media_count
            ) -> bool:
                return (
                    len(current_driver.find_elements(By.CSS_SELECTOR, media_selector))
                    > previous_count
                )

            try:
                WebDriverWait(driver, self._load_more_wait_time).until(
                    media_count_increased
                )
            except TimeoutException:
                break

            media_count = len(driver.find_elements(By.CSS_SELECTOR, media_selector))

    @property
    def _user_name(self) -> str:
        path = urlparse(self.feed.url).path.rstrip("/")
        return path.rsplit("/", 1)[-1].removeprefix("@")
