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
    _http_response_storage_time = timedelta(seconds=0)
    _cache_storage_time = timedelta(seconds=0)
    _cache_storage_time_if_success = timedelta(days=1)
    _selenium_wait_time = 10
    _should_delete_cookies = True
    _service_url = "https://storiesig.website/"

    @override
    async def _generate_hash(self, item: Item) -> str:
        return await HashService.hash_video_from_url(item.link)

    @property
    async def items(self) -> list[Item]:
        soup = await self.get_soup(self._service_url)
        videos = soup.find_all("video")

        items = []
        for v in videos:
            if not isinstance(v, Tag):
                continue
            if not v.source or "src" not in v.source.attrs:
                continue
            items.append(
                Item(
                    title="inst: " + self._user_name,
                    text=self._user_name,
                    date=constant_datetime,
                    link=str(v.source["src"]),
                )
            )
        return items

    @override
    def make_actions(self, driver: WebDriver):
        # Click consent button on startup
        try:
            button = driver.find_element(
                By.XPATH,
                "/html/body/div[2]/div[2]/div[2]/div[2]/div[2]/button[1]",
            )
            driver.execute_script("arguments[0].click();", button)
        except NoSuchElementException:
            pass

        # Insert account name in form
        link = driver.find_element(By.ID, "link")  # Replace with actual element ID
        link.send_keys(self.feed.url)
        time.sleep(self._selenium_wait_time)

        # Click dowbload button
        button = driver.find_element(
            By.ID,
            "btn-download",
        )
        driver.execute_script("arguments[0].click();", button)

        time.sleep(self._selenium_wait_time)

    @property
    def _user_name(self) -> str:
        return self.feed.url.split("/")[-1]
