import time
from typing import override
from datetime import timedelta

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By

from app.utils.datetime import constant_datetime
from app.extentions.parsers.selenium import SeleniumParserExtention
from app.serializers.feed import Item


class InstagramStoriesFeed(SeleniumParserExtention):
    _cache_storage_time_if_success = timedelta(days=1)
    _selenium_wait_time = 5
    _service_url = "https://storiesig.website/"

    @property
    async def items(self) -> list[Item]:
        soup = await self.get_soup(self._service_url)
        videos = soup.find_all("video")

        return [
            Item(
                title="inst: " + self._user_name,
                text=self._user_name,
                date=constant_datetime,
                link=v.source["src"],
            )
            for v in videos
        ]

    @override
    def make_actions(self, driver: WebDriver):
        # Click consent button on startup
        button = driver.find_element(
            By.XPATH,
            "/html/body/div[2]/div[2]/div[2]/div[2]/div[2]/button[1]",
        )
        driver.execute_script("arguments[0].click();", button)

        # Insert account name in form
        link = driver.find_element(By.ID, "link")  # Replace with actual element ID
        link.send_keys(self.feed.url)
        time.sleep(self._selenium_wait_time)

        # Click dowbload button
        button = driver.find_element(
            By.ID,
            "downloadButton",
        )
        button.click()

        time.sleep(self._selenium_wait_time)

    @property
    def _user_name(self) -> str:
        return self.feed.url.split("/")[-1]
