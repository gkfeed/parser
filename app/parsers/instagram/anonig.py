import asyncio
import re
from datetime import timedelta
from html import escape
from typing import Literal, override
from urllib.parse import urlparse

import structlog
from bs4 import BeautifulSoup
from bs4.element import Tag
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.exceptions import FeedUnavailable
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.serializers.feed import Item
from app.services.hash import HashService
from app.services.http import HttpRequestError
from app.services.image import ImageService
from app.utils.datetime import constant_datetime

logger = structlog.get_logger(__name__)


class InstagramFeed(ItemsHashExtension, SeleniumParserExtension, CacheFeedExtension):
    """Embed still images and deduplicate by their content.

    Videos are represented by embedded thumbnails, without temporary video URLs.
    Videos without thumbnails are skipped.
    """

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
        match = re.search(r'src="data:[^;]+;base64,([^"]+)"', item.text)
        if match:
            return HashService.hash_str(match.group(1))
        return HashService.hash_str(item.text)

    async def _parse_items(self) -> list[Item]:
        soup = await self.get_soup(self._service_url)
        media = soup.select(".search-result .profile-media-list__item")
        semaphore = asyncio.Semaphore(self._image_download_concurrency)

        async def create_item(item: Tag) -> Item | None:
            async with semaphore:
                return await self._create_item_from_media(item)

        items = await asyncio.gather(*(create_item(item) for item in media))
        # Videos without thumbnails have no durable media to publish.
        return [item for item in items if item is not None]

    @override
    def _validate_html(self, url: str, html: bytes) -> None:
        soup = BeautifulSoup(html, "html.parser")
        result = soup.select_one(".search-result")
        if result is None:
            raise FeedUnavailable(self.feed.url, "missing_search_result")
        if result.select_one(".loader-component") is not None:
            raise FeedUnavailable(self.feed.url, "media_loading_unverified")
        error = result.select_one(".error-message__text")
        if error is None:
            error = result.select_one(".error-message")
        if error is not None and error.get_text(strip=True):
            self._check_error(error.get_text(" ", strip=True))
            if result.select_one(".profile-media-list__item") is not None:
                raise ValueError(
                    "Anonyig response contains both media and an empty result"
                )
            return
        if result.select_one(".profile-media-list__item") is None:
            raise FeedUnavailable(self.feed.url, "empty_unverified")

    async def _create_item_from_media(self, media: Tag) -> Item | None:
        is_video = media.find(class_="tags__item--video") is not None
        img = media.select_one("img")
        if img is None:
            if is_video:
                logger.info("anonyig_media_skipped", reason="missing_video_thumbnail")
                return None
            raise ValueError("Anonyig media is missing an image")

        src = img.get("src")
        if not isinstance(src, str) or not src.strip():
            if is_video:
                logger.info("anonyig_media_skipped", reason="missing_video_thumbnail")
                return None
            raise ValueError("Anonyig image is missing a valid src")
        src = src.strip()

        image_url = escape(await self._embedded_image_url(src), quote=True)
        username = escape(self._user_name, quote=True)
        img_tag = f'<img src="{image_url}" alt="{username}" />'
        label = "<br>Video thumbnail" if is_video else ""

        return Item(
            title="inst: " + self._user_name,
            text=f"{username}{label}<br>{img_tag}",
            date=constant_datetime,
            link=self.feed.url,
        )

    async def _embedded_image_url(self, src: str) -> str:
        if src.startswith("data:"):
            image = await ImageService.from_data_url(src)
            # The source's base64 spelling is part of the existing item identity.
            return f"data:{image.mime_type};base64,{src.partition(',')[2]}"

        self._validate_image_url(src)
        try:
            image = await ImageService.download(src)
        except HttpRequestError as exc:
            raise FeedUnavailable(self.feed.url, "image_download_failed") from exc
        return await asyncio.to_thread(lambda: image.data_url)

    @staticmethod
    def _validate_image_url(src: str) -> None:
        if any(char.isspace() or ord(char) < 32 for char in src) or "\\" in src:
            raise ValueError("Anonyig image has an invalid URL")
        try:
            parsed = urlparse(src)
            port = parsed.port
        except ValueError as exc:
            raise ValueError("Anonyig image has an invalid URL") from exc
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or port == 0
            or any(char in src for char in '<>"\x7f')
        ):
            raise ValueError("Anonyig image has an invalid URL")

    @override
    def make_actions(self, driver: WebDriver):
        try:
            self._search_media(driver)
        except (NoSuchElementException, TimeoutException) as exc:
            raise FeedUnavailable(self.feed.url, "browser_action_failed") from exc

    def _search_media(self, driver: WebDriver) -> None:
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
                self._loaded_error,
                expected_conditions.presence_of_element_located(
                    (By.CSS_SELECTOR, ".search-result .profile-media-list__item")
                ),
            )
        )
        if not isinstance(result, WebElement):
            raise FeedUnavailable(self.feed.url, "browser_action_failed")
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

    @staticmethod
    def _loaded_error(driver: WebDriver) -> WebElement | Literal[False]:
        if driver.find_elements(By.CSS_SELECTOR, ".search-result .loader-component"):
            return False
        for error in driver.find_elements(
            By.CSS_SELECTOR, ".search-result .error-message"
        ):
            texts = error.find_elements(By.CSS_SELECTOR, ".error-message__text")
            text = texts[0] if texts else error
            if (text.get_attribute("textContent") or "").strip():
                return error
        return False

    def _check_error(self, message: str) -> None:
        message = " ".join(message.lower().split()).rstrip(".! ")
        if message in ("no posts", "no posts found", "no publications found"):
            logger.info("anonyig_posts_empty")
            return
        if "private" in message:
            raise FeedUnavailable(self.feed.url, "private")
        if any(
            text in message
            for text in ("user not found", "profile not found", "account not found")
        ):
            raise FeedUnavailable(self.feed.url, "not_found")
        raise FeedUnavailable(self.feed.url, "upstream_error")

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

            def media_loading_finished(
                current_driver: WebDriver, previous_count: int = media_count
            ) -> bool:
                return (
                    len(current_driver.find_elements(By.CSS_SELECTOR, media_selector))
                    > previous_count
                ) or not current_driver.find_elements(By.CSS_SELECTOR, trigger_selector)

            try:
                WebDriverWait(driver, self._load_more_wait_time).until(
                    media_loading_finished
                )
            except TimeoutException as exc:
                raise FeedUnavailable(self.feed.url, "media_loading_timeout") from exc

            media_count = len(driver.find_elements(By.CSS_SELECTOR, media_selector))

    @property
    def _user_name(self) -> str:
        path = urlparse(self.feed.url).path.rstrip("/")
        return path.rsplit("/", 1)[-1].removeprefix("@")
