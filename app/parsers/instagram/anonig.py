import time
from typing import override
from datetime import timedelta

from bs4.element import Tag
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

from app.utils.datetime import constant_datetime
from app.serializers.feed import Item
from app.services.hash import HashService
from app.services.catbox import CatboxUploader
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.extensions.parsers.hash import ItemsHashExtension


class InstagramFeed(ItemsHashExtension, SeleniumParserExtension, CacheFeedExtension):
    _http_response_storage_time = timedelta(seconds=0)  # url is similar
    _cache_storage_time_if_success = timedelta(days=1)
    _selenium_wait_time = 10
    _should_delete_cookies = True
    _service_url = "https://anonyig.com/en/"

    @override
    async def _generate_hash(self, item: Item) -> str:
        # FIXME: hash_file_from_url
        return await HashService.hash_video_from_url(item.link)

    @property
    async def items(self) -> list[Item]:
        soup = await self.get_soup(self._service_url)

        media_list_items = soup.find_all(class_="profile-media-list__item")

        items = []
        for i in media_list_items:
            if not isinstance(i, Tag):
                continue

            item = await self._create_item_from_media(i)
            if item:
                items.append(item)

        return items

    async def _create_item_from_media(self, media: Tag) -> Item | None:
        img = media.find("img")
        if not isinstance(img, Tag):
            return None

        src = img.get("src")
        if isinstance(src, list):
            src = src[0]

        if not src or not isinstance(src, str):
            return None

        link = await CatboxUploader.upload_with_url(src)

        return Item(
            title="inst: " + self._user_name,
            text=self._user_name,
            date=constant_datetime,
            link=link,
        )

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

        # Insert account name in form
        link = driver.find_element(
            By.CSS_SELECTOR, "form.search-form input.search-form__input"
        )
        link.send_keys(self._user_name)
        time.sleep(1)

        # Click search button
        button = driver.find_element(
            By.CSS_SELECTOR,
            ".search-form__button",
        )
        driver.execute_script("arguments[0].click();", button)

        time.sleep(self._selenium_wait_time)
        for _ in range(10):
            driver.execute_script("window.scrollBy(0, 500);")
            time.sleep(1)

    @property
    def _user_name(self) -> str:
        return self.feed.url.split("/")[-1]
