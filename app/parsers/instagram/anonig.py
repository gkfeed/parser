import asyncio
import base64
import re
from datetime import timedelta
from typing import override
from urllib.parse import urlparse

from bs4.element import Tag
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.serializers.feed import Item
from app.services.hash import HashService
from app.services.http import HttpRequestError
from app.utils.datetime import constant_datetime
from app.workers.http import get_html


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

    @property
    async def items(self) -> list[Item]:
        soup = await self.get_soup(self._service_url)

        media_list_items = soup.find_all(class_="profile-media-list__item")

        media = [item for item in media_list_items if isinstance(item, Tag)]
        semaphore = asyncio.Semaphore(self._image_download_concurrency)

        async def create_item(item: Tag) -> Item | None:
            async with semaphore:
                return await self._create_item_from_media(item)

        items = await asyncio.gather(*(create_item(item) for item in media))
        return [item for item in items if item is not None]

    @staticmethod
    def _get_mime_type(data: bytes) -> str:
        if data.startswith(b"\xff\xd8"):
            return "image/jpeg"
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if data.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
            return "image/webp"
        return "image/jpeg"

    async def _create_item_from_media(self, media: Tag) -> Item | None:
        img = media.find("img")
        if not isinstance(img, Tag):
            return None

        is_video = media.find(class_="tags__item--video") is not None

        link_tag = media.find("a")
        media_url = link_tag.get("href") if isinstance(link_tag, Tag) else None

        if is_video and isinstance(media_url, str) and ".mp4" in media_url:
            print(
                f"warning: Instagram video is tmp unavailable because media links expire: {media_url}"
            )
            # video_html = (
            #     f'<video src="{media_url}" controls preload="metadata" '
            #     f'style="max-width: 100%; height: auto;"></video>'
            # )
            # return Item(
            #     title="inst: " + self._user_name,
            #     text=f"{self._user_name}<br>{video_html}",
            #     date=constant_datetime,
            #     link=self.feed.url,
            # )
            return None

        src = img.get("src")
        if isinstance(src, list):
            src = src[0]

        if not src or not isinstance(src, str):
            return None

        if src.startswith("data:"):
            # Handle data URI
            try:
                header, encoded = src.split(",", 1)
                mime_type = header.split(";")[0].split(":")[1]
                # encoded is already base64 string
            except (ValueError, IndexError):
                return None
        else:
            # Handle remote URL
            try:
                img_bytes = await get_html(src)
                encoded = base64.b64encode(img_bytes).decode("utf-8")
                mime_type = self._get_mime_type(img_bytes)
            except HttpRequestError:
                return None

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

    @staticmethod
    def _click(driver: WebDriver, element: WebElement) -> None:
        try:
            driver.execute_script("arguments[0].click();", element)
        except TimeoutException:
            # Background requests can outlive an otherwise usable result page.
            pass

    @property
    def _user_name(self) -> str:
        path = urlparse(self.feed.url).path.rstrip("/")
        return path.rsplit("/", 1)[-1].removeprefix("@")
