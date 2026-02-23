from datetime import timedelta
import time
from typing import override

from bs4 import Tag
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By

from app.utils.datetime import constant_datetime
from app.services.hash import HashService
from app.serializers.feed import Item
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemsHashExtension


class VkFeed(ItemsHashExtension, SeleniumParserExtension, CacheFeedExtension):
    _cache_storage_time = timedelta(hours=1)
    _selenium_wait_time = 5

    @property
    async def items(self) -> list[Item]:
        return [
            Item(
                title=self._get_post_title(p),
                text=self._get_post_text(p),
                date=constant_datetime,
                link=self._get_post_link(p),
            )
            for p in await self._posts
        ]

    @override
    async def _generate_hash(self, item: Item) -> str:
        return HashService.hash_str(item.link)

    @property
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)
        return [p for p in soup.find_all(class_="wall_post_cont") if isinstance(p, Tag)]

    @override
    def make_actions(self, driver: WebDriver):
        # Bypass robot check if present
        try:
            buttons = driver.find_elements(By.CLASS_NAME, "start")
            if buttons:
                buttons[0].click()
                time.sleep(5)
        except Exception:
            pass

    def _get_post_title(self, post: Tag) -> str:
        # Try to find author name in the same page or use feed title
        try:
            author = post.find_all(class_="PostHeaderTitle__authorName")
            if author:
                return author[0].text
            return self.feed.title or "VK Post"
        except (IndexError, AttributeError):
            return "VK Post"

    def _get_post_text(self, post: Tag) -> str:
        try:
            if item := post.find(class_="vkitShowMoreText__text--vRrhr"):
                return item.text

            if item := post.find(class_="wall_post_text"):
                return item.text

            return ""
        except Exception:
            return ""

    def _get_post_link(self, post: Tag) -> str:
        post_id = post.get("id")

        if not isinstance(post_id, str):
            raise ValueError("Post ID is not a string")

        if not post_id.startswith("wpt"):
            raise ValueError(f"Could not extract post link for post: {post_id}")

        raw_id = post_id[3:]
        clean_id = raw_id if raw_id.startswith("-") else f"-{raw_id}"
        return f"https://vk.com/wall{clean_id}"
