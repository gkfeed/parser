import asyncio
import time
from datetime import UTC, datetime, timedelta
from typing import Literal, override

import structlog
from bs4 import Tag
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.exceptions import FeedUnavailable
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.serializers.feed import Item
from app.services.hash import HashService
from app.services.media_upload import FallbackUploader
from app.utils.datetime import constant_datetime

logger = structlog.get_logger(__name__)


class InstagramStoriesFeed(
    ItemsHashExtension, SeleniumParserExtension, CacheFeedExtension
):
    _http_response_storage_time = timedelta(seconds=0)  # url is similar
    _cache_storage_time_if_success = timedelta(days=1)
    _selenium_wait_time = 10
    _page_load_timeout_seconds = 30
    _results_wait_time = 30
    _should_delete_cookies = True
    _service_url = "https://anonyig.com/en/iganony/"
    # This ad player creates/detaches nested frames that can hang ChromeDriver.
    _blocked_url_patterns = ("*://player.avplayer.com/*",)

    @override
    async def _generate_hash(self, item: Item) -> str:
        try:
            return await HashService.hash_video_from_url(item.link)
        except Exception:  # noqa: BLE001 - persisted media can be temporarily unavailable
            return HashService.hash_str(item.link)

    async def _parse_items(self) -> list[Item]:
        soup = await self.get_soup(self._service_url)
        uploads = await asyncio.gather(
            *(self._upload_media(link) for link in self._extract_media_links(soup))
        )
        links = [link for link in uploads if link is not None]
        logger.info("stories_media_processed", found=len(uploads), uploaded=len(links))
        if uploads and not links:
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

    @staticmethod
    async def _upload_media(url: str) -> str | None:
        return await FallbackUploader.upload_with_url(url)

    @staticmethod
    def _extract_media_links(soup: Tag) -> list[str]:
        active_tab = soup.select_one(".tabs-component__button--active")
        if not isinstance(active_tab, Tag):
            return []
        if active_tab.get_text(strip=True).lower() != "stories":
            return []

        links = []
        for media in soup.select(".profile-media-list__item"):
            download = media.select_one("a.download-btn[href]")
            if isinstance(download, Tag):
                href = download.get("href")
                if isinstance(href, str):
                    links.append(href)
        return links

    @override
    def make_actions(self, driver: WebDriver) -> None:
        # The results page keeps some requests open in Docker, so a synchronous
        # click can otherwise wait for Selenium's five-minute default timeout.
        driver.set_page_load_timeout(30)

        try:
            button = driver.find_element(
                By.XPATH,
                "/html/body/div/div[2]/div[2]/div[3]/div[2]/button[1]",
            )
            self._click(driver, button)
        except NoSuchElementException:
            pass

        wait = WebDriverWait(driver, self._results_wait_time)
        links = wait.until(
            EC.visibility_of_any_elements_located(
                (By.CSS_SELECTOR, "form.search-form input.search-form__input")
            )
        )
        driver.execute_script(
            """
            arguments[0].value = arguments[1];
            arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
            """,
            links[0],
            self._user_name,
        )

        button = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "form.search-form .search-form__button")
            )
        )
        self._click(driver, button)

        stories_button = (
            "//button[contains(@class, 'tabs-component__button') "
            "and normalize-space(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            "'abcdefghijklmnopqrstuvwxyz')) = 'stories']"
        )
        result = wait.until(
            EC.any_of(
                EC.presence_of_element_located((By.XPATH, stories_button)),
                self._loaded_error,
            )
        )
        result_classes = (result.get_attribute("class") or "").split()
        if "error-message__text" in result_classes:
            self._check_error(result)
            return
        if (
            "tabs-component__button--disabled" in result_classes
            or not result.is_enabled()
            or result.get_attribute("aria-disabled") == "true"
        ):
            raise self._unavailable("private")
        self._click(driver, result)
        media_ready = EC.all_of(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    stories_button
                    + "[contains(@class, 'tabs-component__button--active')]",
                )
            ),
            # The subscription landing hides results while requests still run.
            # A hidden loader is not evidence that loading has finished.
            EC.none_of(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".search-result .loader-component")
                )
            ),
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    ".search-result .profile-media-list__item a.download-btn[href]",
                )
            ),
        )
        stories_result = wait.until(EC.any_of(self._loaded_error, media_ready))
        if isinstance(stories_result, WebElement):
            self._check_error(stories_result)
            return

        for _ in range(3):
            driver.execute_script("window.scrollBy(0, 500);")
            time.sleep(1)

    @staticmethod
    def _loaded_error(driver: WebDriver) -> WebElement | Literal[False]:
        if driver.find_elements(By.CSS_SELECTOR, ".search-result .loader-component"):
            return False
        # Anonyig's subscription landing can hide the whole search result.
        # Read the actual error text, excluding the fallback popup's ad copy.
        for error in driver.find_elements(
            By.CSS_SELECTOR, ".search-result .error-message__text"
        ):
            if (error.get_attribute("textContent") or "").strip():
                return error
        return False

    def _check_error(self, error: WebElement) -> None:
        message = (error.get_attribute("textContent") or "").lower()
        if "no stories" in message:
            # Anonyig also uses this message for upstream failures.
            logger.warning("stories_empty_unverified")
            return
        if "private" in message:
            raise self._unavailable("private")
        if any(
            text in message
            for text in ("user not found", "profile not found", "account not found")
        ):
            raise self._unavailable("not_found")
        raise self._unavailable("upstream_error")

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
