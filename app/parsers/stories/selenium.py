import time
from typing import override
from datetime import timedelta

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

from bs4 import Tag

from app.utils.datetime import constant_datetime
from app.serializers.feed import Item
from app.services.hash import HashService
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.extensions.parsers.hash import ItemsHashExtension


class InstagramStoriesFeed(
    ItemsHashExtension, SeleniumParserExtension, CacheFeedExtension
):
    _http_response_storage_time = timedelta(seconds=0)  # url is similar
    _cache_storage_time_if_success = timedelta(days=1)
    _selenium_wait_time = 10
    _should_delete_cookies = True
    _service_url = "https://anonyig.com/en/"

    @override
    async def _generate_hash(self, item: Item) -> str:
        return await HashService.hash_video_from_url(item.link)

    @property
    async def items(self) -> list[Item]:
        soup = await self.get_soup(self._service_url)

        return [
            Item(
                title="inst: " + self._user_name,
                text=self._user_name,
                date=constant_datetime,
                link=link,
            )
            for link in self._extract_media_links(soup)
        ]

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
        try:
            button = driver.find_element(
                By.XPATH,
                "/html/body/div/div[2]/div[2]/div[3]/div[2]/button[1]",
            )
            driver.execute_script("arguments[0].click();", button)
        except NoSuchElementException:
            pass

        link = driver.find_element(
            By.CSS_SELECTOR, "form.search-form input.search-form__input"
        )
        link.send_keys(self._user_name)

        button = driver.find_element(By.CSS_SELECTOR, ".search-form__button")
        driver.execute_script("arguments[0].click();", button)
        time.sleep(self._selenium_wait_time)

        tabs = driver.find_elements(By.CSS_SELECTOR, ".tabs-component__button")
        if len(tabs) > 1:
            driver.execute_script("arguments[0].click();", tabs[1])
            time.sleep(self._selenium_wait_time)

        for _ in range(3):
            driver.execute_script("window.scrollBy(0, 500);")
            time.sleep(1)

    @property
    def _user_name(self) -> str:
        return self.feed.url.split("/")[-1]
