import asyncio
import time
from datetime import timedelta
from typing import override

from bs4 import Tag
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
from app.services.media_upload import FallbackUploader
from app.utils.datetime import constant_datetime


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

    @override
    async def _generate_hash(self, item: Item) -> str:
        try:
            return await HashService.hash_video_from_url(item.link)
        except Exception:  # noqa: BLE001 - persisted media can be temporarily unavailable
            return HashService.hash_str(item.link)

    @property
    async def items(self) -> list[Item]:
        soup = await self.get_soup(self._service_url)
        links = await asyncio.gather(
            *(self._upload_media(link) for link in self._extract_media_links(soup))
        )

        return [
            Item(
                title="inst: " + self._user_name,
                text=self._user_name,
                date=constant_datetime,
                link=link,
            )
            for link in links
            if link is not None
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
    def make_actions(self, driver: WebDriver):
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

        link = driver.find_element(
            By.CSS_SELECTOR, "form.search-form input.search-form__input"
        )
        link.send_keys(self._user_name)

        button = driver.find_element(By.CSS_SELECTOR, ".search-form__button")
        self._click(driver, button)

        result = WebDriverWait(driver, self._results_wait_time).until(
            expected_conditions.any_of(
                expected_conditions.presence_of_element_located(
                    (
                        By.XPATH,
                        (
                            "//button[contains(@class, 'tabs-component__button') "
                            "and normalize-space(translate(., "
                            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
                            "'abcdefghijklmnopqrstuvwxyz')) = 'stories']"
                        ),
                    )
                ),
                expected_conditions.presence_of_element_located(
                    (By.CSS_SELECTOR, ".error-message")
                ),
            )
        )
        result_classes = (result.get_attribute("class") or "").split()
        if "error-message" in result_classes:
            return

        self._click(driver, result)
        WebDriverWait(driver, self._results_wait_time).until(
            expected_conditions.presence_of_element_located(
                (
                    By.XPATH,
                    (
                        "//button[contains(@class, "
                        "'tabs-component__button--active') "
                        "and normalize-space(translate(., "
                        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
                        "'abcdefghijklmnopqrstuvwxyz')) = 'stories']"
                    ),
                )
            )
        )
        time.sleep(self._selenium_wait_time)

        for _ in range(3):
            driver.execute_script("window.scrollBy(0, 500);")
            time.sleep(1)

    @staticmethod
    def _click(driver: WebDriver, element: WebElement) -> None:
        try:
            driver.execute_script("arguments[0].click();", element)
        except TimeoutException:
            # The DOM is usable even when background resources never finish.
            pass

    @property
    def _user_name(self) -> str:
        return self.feed.url.split("/")[-1]
