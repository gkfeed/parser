import html
import re
from datetime import UTC, datetime, timedelta
from typing import override
from urllib.parse import urlparse

from bs4 import Tag
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.exceptions import UnavailableFeed
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.serializers.feed import Item
from app.services.hash import HashService
from app.utils.datetime import constant_datetime, convert_datetime


class VkFeed(
    PostToItemsMixin,
    ItemsHashExtension,
    SeleniumParserExtension,
    CacheFeedExtension,
):
    _cache_storage_time = timedelta(hours=1)
    _selenium_wait_time = 5
    _post_selector = '[data-testid="post"][data-post-id]'
    _challenge_attempts = 3

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)
        posts = soup.select(self._post_selector)
        if posts:
            return posts
        legacy_posts = [
            post
            for post in soup.find_all(class_="wall_post_cont")
            if isinstance(post, Tag)
        ]
        if legacy_posts:
            return legacy_posts

        if soup.select_one("button.start"):
            raise UnavailableFeed(self.feed.url)

        return []

    @override
    async def _generate_hash(self, item: Item) -> str:
        return HashService.hash_str(item.link)

    @override
    def make_actions(self, driver: WebDriver):
        try:
            for _ in range(self._challenge_attempts):
                if driver.find_elements(By.CSS_SELECTOR, self._post_selector):
                    return

                buttons = driver.find_elements(By.CSS_SELECTOR, "button.start")
                if not buttons:
                    return

                button = buttons[0]
                button.click()
                wait = WebDriverWait(driver, 30)
                wait.until(ec.staleness_of(button))
                wait.until(
                    ec.presence_of_element_located(
                        (
                            By.CSS_SELECTOR,
                            f"{self._post_selector}, .wall_post_cont, button.start",
                        )
                    )
                )

            if driver.find_elements(By.CSS_SELECTOR, "button.start"):
                raise UnavailableFeed(self.feed.url)
        except (TimeoutException, WebDriverException) as error:
            raise UnavailableFeed(self.feed.url) from error

    @override
    async def _get_post_title(self, post: Tag) -> str:
        # Try to find author name in the same page or use feed title
        author = post.select_one(
            '.PostHeaderTitle__authorName, [data-testid="post-header-title"]'
        )
        return author.get_text(strip=True) if author else self.feed.title or "VK Post"

    @override
    async def _get_post_text(self, post: Tag) -> str:
        text = ""
        show_more_text = post.select_one('[data-testid^="showmoretext-in"]')
        if show_more_text:
            text = show_more_text.get_text("\n", strip=True)
        else:
            wall_text = post.find(class_="wall_post_text")
            if isinstance(wall_text, Tag):
                text = wall_text.get_text("\n", strip=True)

        image_url = self._get_post_image_url(post)
        if not image_url:
            return text

        image = f'<img src="{html.escape(image_url, quote=True)}" alt="VK post">'
        return f"{image}<br>{html.escape(text)}" if text else image

    def _get_post_image_url(self, post: Tag) -> str | None:
        image = post.select_one(
            'a[href*="/photo"] img[src], '
            'a[href*="photo-"] img[src], '
            '[data-testid*="photo" i] img[src], '
            '[class*="PhotoPrimaryAttachment"] img[src], '
            '[class*="MediaGrid"] img[src]'
        )
        if isinstance(image, Tag):
            source = image.get("src")
            if isinstance(source, str) and self._is_http_url(source):
                return source

        thumbnail = post.select_one(
            'a[href*="/photo"][style*="background-image"], '
            'a[href*="photo-"][style*="background-image"], '
            '.page_post_thumb_wrap[style*="background-image"]'
        )
        if isinstance(thumbnail, Tag):
            style = thumbnail.get("style")
            if isinstance(style, str):
                match = re.search(
                    r'background-image\s*:\s*url\((["\']?)(.*?)\1\)', style
                )
                if match and self._is_http_url(match.group(2)):
                    return match.group(2)

        return None

    @staticmethod
    def _is_http_url(value: str) -> bool:
        return urlparse(value).scheme in {"http", "https"}

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
            today_str = datetime.now(UTC).date().strftime("%m/%d/%Y")
            datetime_str = today_str + datetime_str.split("at")[1]

        if datetime_str.startswith("yesterday"):
            yesterday = datetime.now(UTC).date() - timedelta(days=1)
            yesterday_str = yesterday.strftime("%m/%d/%Y")
            datetime_str = yesterday_str + datetime_str.split("at")[1]

        try:
            return convert_datetime(datetime_str)
        except (IndexError, ValueError) as e:
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
            raise ValueError(  # noqa: TRY004 - malformed page data is a value error
                "Post ID is not a string"
            )

        clean_id = post_id if post_id.startswith("-") else f"-{post_id}"
        return f"https://vk.com/wall{clean_id}"
