from datetime import timedelta, datetime, date
from typing import override

from bs4 import Tag
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

from app.utils.datetime import convert_datetime, constant_datetime
from app.services.hash import HashService
from app.serializers.feed import Item
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.extensions.parsers.selenium import SeleniumParserExtension


class VkFeed(
    PostToItemsMixin,
    ItemsHashExtension,
    SeleniumParserExtension,
    CacheFeedExtension,
):
    _cache_storage_time = timedelta(hours=1)
    _selenium_wait_time = 5

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)
        posts = soup.select('[data-testid="post"][data-post-id]')
        if posts:
            return posts
        return [
            post
            for post in soup.find_all(class_="wall_post_cont")
            if isinstance(post, Tag)
        ]

    @override
    async def _generate_hash(self, item: Item) -> str:
        return HashService.hash_str(item.link)

    @override
    def make_actions(self, driver: WebDriver):
        # Bypass robot check if present
        try:
            buttons = driver.find_elements(By.CLASS_NAME, "start")
            if buttons:
                buttons[0].click()
                WebDriverWait(driver, 15).until(
                    ec.presence_of_element_located(
                        (By.CSS_SELECTOR, '[data-testid="post"][data-post-id]')
                    )
                )
        except Exception:
            pass

    @override
    async def _get_post_title(self, post: Tag) -> str:
        # Try to find author name in the same page or use feed title
        try:
            author = post.select_one(
                '.PostHeaderTitle__authorName, [data-testid="post-header-title"]'
            )
            if author:
                return author.get_text(strip=True)
            return self.feed.title or "VK Post"
        except (IndexError, AttributeError):
            return "VK Post"

    @override
    async def _get_post_text(self, post: Tag) -> str:
        try:
            show_more_text = post.select_one('[data-testid^="showmoretext-in"]')
            if show_more_text:
                return show_more_text.get_text("\n", strip=True)

            wall_text = post.find(class_="wall_post_text")
            if isinstance(wall_text, Tag):
                return wall_text.get_text("\n", strip=True)

            return ""
        except Exception:
            return ""

    @override
    async def _get_post_datetime(self, post: Tag) -> datetime:
        time_tag = post.find("time")
        if not isinstance(time_tag, Tag):
            return constant_datetime

        datetime_str = time_tag.text.strip()
        if not datetime_str:
            return constant_datetime

        return self._parse_datetime(datetime_str)

    def _parse_datetime(self, datetime_str: str) -> datetime:
        if datetime_str.startswith("today"):
            today_str = date.today().strftime("%m/%d/%Y")
            datetime_str = today_str + datetime_str.split("at")[1]

        if datetime_str.startswith("yesterday"):
            yesterday = date.today() - timedelta(days=1)
            yesterday_str = yesterday.strftime("%m/%d/%Y")
            datetime_str = yesterday_str + datetime_str.split("at")[1]

        try:
            return convert_datetime(datetime_str)
        except Exception as e:
            print(e)
            return constant_datetime

    @override
    async def _get_post_link(self, post: Tag) -> str:
        post_id = post.get("data-post-id")
        if not isinstance(post_id, str):
            element_id = post.get("id")
            if isinstance(element_id, str) and element_id.startswith("wpt"):
                post_id = element_id[3:]

        if not isinstance(post_id, str):
            raise ValueError("Post ID is not a string")

        clean_id = post_id if post_id.startswith("-") else f"-{post_id}"
        return f"https://vk.com/wall{clean_id}"
