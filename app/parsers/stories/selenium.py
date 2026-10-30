import asyncio
from datetime import UTC, datetime, timedelta
from typing import Literal, Never, override
from urllib.parse import urlsplit

import structlog
from bs4 import Tag
from requests.exceptions import RequestException
from selenium.common.exceptions import TimeoutException
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
from app.services.selenium.lazy_list import (
    LazyListLoader,
    LazyListTimeoutError,
    LazyListUnavailableError,
)
from app.utils.datetime import constant_datetime
from app.utils.logging import url_log_fields

logger = structlog.get_logger(__name__)


class InstagramStoriesFeed(
    ItemsHashExtension, SeleniumParserExtension, CacheFeedExtension
):
    _http_response_storage_time = timedelta(seconds=0)  # url is similar
    success_result_delay = timedelta(days=1)
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
        # The results page keeps some requests open in Docker, so a synchronous
        # click can otherwise wait for Selenium's five-minute default timeout.
        driver.set_page_load_timeout(30)

        dismiss_buttons = driver.find_elements(
            By.XPATH,
            "/html/body/div/div[2]/div[2]/div[3]/div[2]/button[1]",
        )
        if dismiss_buttons:
            self._click(driver, dismiss_buttons[0])

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

        self._dismiss_subscription_landing(driver)
        self._load_all_media(driver)

    def _dismiss_subscription_landing(self, driver: WebDriver) -> None:
        buttons = driver.find_elements(
            By.CSS_SELECTOR, ".tz-landing-exp .tz-landing__button-close"
        )
        if not buttons:
            return

        # Anonyig hides loaded results behind its subscription landing. Use its
        # browser-download button so pagination can inspect the visible list.
        self._click(driver, buttons[0])
        try:
            WebDriverWait(driver, self._results_wait_time).until(
                EC.none_of(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".tz-landing-exp"))
                )
            )
        except TimeoutException as exc:
            raise self._unavailable("media_loading_unverified") from exc

    def _load_all_media(self, driver: WebDriver) -> None:
        try:
            LazyListLoader(
                driver,
                items_selector=".search-result .profile-media-list__item",
                trigger_selector=".search-result .profile-media-list .trigger",
            ).load(self._results_wait_time)
        except LazyListUnavailableError as exc:
            raise self._unavailable("media_loading_unverified") from exc
        except LazyListTimeoutError as exc:
            raise self._unavailable("media_loading_timeout") from exc

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

    def _check_error(self, error: WebElement) -> Never:
        message = (error.get_attribute("textContent") or "").lower()
        if "no stories" in message:
            # Anonyig also uses this message for upstream failures.
            logger.warning("stories_empty_unverified")
            raise self._unavailable("empty_unverified")
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
