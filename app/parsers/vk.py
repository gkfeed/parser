import html
import re
from datetime import UTC, datetime, timedelta
from typing import override
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag
from dateutil.parser import parse
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.exceptions import FeedUnavailable
from app.extensions.parsers.hash import ItemLinkHashExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.utils.datetime import constant_datetime, parse_datetime


class VkFeed(
    PostToItemsMixin,
    ItemLinkHashExtension,
    SeleniumParserExtension,
    CacheFeedExtension,
):
    empty_result_delay = timedelta(hours=1)
    _selenium_wait_time = 5
    _post_selector = '[data-testid="post"][data-post-id]'
    _empty_selector = (
        '#page-wall [data-testid="feed-empty-result"], '
        '#page-wall [data-testid="empty_wall"]'
    )
    _empty_card_selector = (
        "#page_wall_posts > .no_rows, "
        # The SPA group page uses an empty newsfeed card without a wall test ID.
        '#spa_layout_content:has([data-testid="group-header"]) '
        "section:has(.vkuiIcon--newsfeed_outline_56)"
    )
    _empty_card_messages = frozenset({"No results found", "The wall is empty."})
    _challenge_attempts = 3

    @override
    def _validate_html(self, url: str, html: bytes) -> None:
        soup = BeautifulSoup(html, "html.parser")
        if soup.select_one(f"{self._post_selector}, .wall_post_cont") is not None:
            return
        if soup.select_one("button.start") is not None:
            raise FeedUnavailable(url, "browser_challenge")
        if soup.select_one(self._empty_selector) is not None:
            return
        if any(
            card.get_text(" ", strip=True) in self._empty_card_messages
            for card in soup.select(self._empty_card_selector)
        ):
            return
        raise FeedUnavailable(url, "missing_wall")

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
        return legacy_posts

    @override
    def make_actions(self, driver: WebDriver):
        for _ in range(self._challenge_attempts):
            if self._attempt_challenge(driver):
                return

        raise FeedUnavailable(self.feed.url, "browser_challenge")

    def _attempt_challenge(self, driver: WebDriver) -> bool:
        posts = ec.presence_of_all_elements_located(
            (By.CSS_SELECTOR, f"{self._post_selector}, .wall_post_cont")
        )
        empty = ec.any_of(
            ec.presence_of_element_located((By.CSS_SELECTOR, self._empty_selector)),
            self._empty_wall_card,
        )
        page_ready = ec.any_of(posts, empty)
        start = ec.element_to_be_clickable((By.CSS_SELECTOR, "button.start"))
        challenge_error = ec.visibility_of_element_located((By.CSS_SELECTOR, ".error"))
        wait = WebDriverWait(driver, 30)
        try:
            if page_ready(driver):
                return True

            buttons = driver.find_elements(By.CSS_SELECTOR, "button.start")
            if not buttons:
                wait.until(page_ready)
                return True

            button = wait.until(start)
            button.click()
            # Hiding the button starts the challenge; it does not finish it.
            wait.until(
                ec.any_of(
                    page_ready, challenge_error, ec.invisibility_of_element(button)
                )
            )
            wait.until(ec.any_of(page_ready, challenge_error, start))
            if page_ready(driver):
                return True
            if not start(driver):
                raise FeedUnavailable(self.feed.url, "browser_challenge")

            return False
        except (TimeoutException, WebDriverException) as error:
            raise FeedUnavailable(self.feed.url, "browser_action_failed") from error

    def _empty_wall_card(self, driver: WebDriver) -> bool:
        # A generic placeholder can also contain an access or loading error.
        return any(
            card.text.strip() in self._empty_card_messages
            for card in driver.find_elements(By.CSS_SELECTOR, self._empty_card_selector)
        )

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
        if not isinstance(thumbnail, Tag):
            return None

        style = thumbnail.get("style")
        if not isinstance(style, str):
            return None

        match = re.search(r'background-image\s*:\s*url\((["\']?)(.*?)\1\)', style)
        if not match or not self._is_http_url(match.group(2)):
            return None

        return match.group(2)

    @staticmethod
    def _is_http_url(value: str) -> bool:
        return urlparse(value).scheme in {"http", "https"}

    @override
    async def _get_post_datetime(self, post: Tag) -> datetime:
        for time_tag in post.select('[data-testid="post_date_block_preview"], time'):
            owner = time_tag.find_parent(attrs={"data-testid": "post"})
            if owner is None or owner is post:
                break
        else:
            return constant_datetime

        datetime_str = time_tag.get_text(" ", strip=True)
        if time_tag.get("data-testid") == "post_date_block_preview":
            return self._parse_post_day(datetime_str)
        if not datetime_str:
            return constant_datetime
        return self._parse_datetime(datetime_str)

    @staticmethod
    def _parse_post_day(value: str) -> datetime:
        # Relative previews cannot reliably identify a calendar day. Keep the
        # constant rather than guessing from the current time or browser state.
        if re.fullmatch(r"just now|\d+\s+(min|h|d)\s+ago", value, re.IGNORECASE):
            return constant_datetime
        try:
            parsed = parse(value)
        except (ValueError, OverflowError) as error:
            raise ValueError(f"Invalid VK post date: {value!r}") from error
        return parsed.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)

    def _parse_datetime(self, datetime_str: str) -> datetime:
        if datetime_str.startswith(("today", "yesterday")):
            match = re.fullmatch(r"(today|yesterday)\s+at\s+(.+)", datetime_str)
            if match is None:
                raise ValueError(f"Invalid VK relative date: {datetime_str!r}")

            relative_date = datetime.now(UTC).date()
            if match.group(1) == "yesterday":
                relative_date -= timedelta(days=1)
            datetime_str = f"{relative_date.isoformat()} {match.group(2)}"

        return parse_datetime(datetime_str)

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
