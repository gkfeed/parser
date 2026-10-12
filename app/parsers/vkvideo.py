from datetime import UTC, datetime
from typing import Any, ClassVar, override
from urllib.parse import urljoin, urlsplit, urlunsplit

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

from app.extensions.parsers.exceptions import UnavailableFeed
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.serializers.feed import Item
from app.services.hash import HashService
from app.services.ytdlp import BaseExtractionMode, YtdlpInfoExtractor
from app.utils.datetime import constant_datetime


class VkVideoExtractionMode(BaseExtractionMode):
    opts: ClassVar[dict[str, Any]] = {
        **BaseExtractionMode.opts,
        "extract_flat": False,
        "skip_download": True,
    }


class VkVideoFeed(ItemsHashExtension, SeleniumParserExtension):
    _max_videos = 5
    _page_load_timeout_seconds = 30
    _video_selector = (
        '[data-testid="catalog_item_video"], [data-testid="video_card_layout"]'
    )
    _video_link_selector = '[data-testid="video_card_title"] a[href*="/video"]'
    _challenge_attempts = 4

    async def _parse_items(self) -> list[Item]:
        try:
            info = await YtdlpInfoExtractor.extract_channel_videos_info(
                self.feed.url, VkVideoExtractionMode(), self._max_videos
            )
        except ValueError:
            return await self._parse_page_items()

        channel = info.get("title") or self.feed.title
        items = []
        for video in info["entries"]:
            if not video:
                continue

            video_id = video.get("id")
            link = (
                f"https://vkvideo.ru/video{video_id}"
                if video_id
                else video.get("webpage_url") or video.get("url")
            )
            if not link:
                continue

            timestamp = video.get("timestamp") or video.get("release_timestamp")
            upload_date = video.get("upload_date")
            if timestamp:
                published_at = datetime.fromtimestamp(timestamp, UTC)
            elif upload_date:
                published_at = datetime.strptime(upload_date, "%Y%m%d").replace(
                    tzinfo=UTC
                )
            else:
                published_at = constant_datetime

            items.append(
                Item(
                    title=f"VK Video: {channel}",
                    text=video.get("title") or "VK Video",
                    date=published_at,
                    link=link,
                )
            )

        return items

    def _get_target_url(self) -> str:
        url = urlsplit(self.feed.url)
        parts = url.path.strip("/").split("/")
        if len(parts) == 1 and parts[0].startswith("@"):
            return urlunsplit(url._replace(path=f"/{parts[0]}/all"))
        return self.feed.url

    @override
    def make_actions(self, driver: WebDriver) -> None:
        target = self._get_target_url()
        target_path = urlsplit(target).path.rstrip("/")
        wait = WebDriverWait(driver, 30)
        try:
            # Leave room to reopen the channel after the verification redirects.
            for _ in range(self._challenge_attempts + 2):
                wait.until(
                    ec.presence_of_element_located(
                        (By.CSS_SELECTOR, f"button.start, {self._video_link_selector}")
                    )
                )
                buttons = driver.find_elements(By.CSS_SELECTOR, "button.start")
                if buttons:
                    wait.until(ec.element_to_be_clickable(buttons[0])).click()
                    wait.until(ec.staleness_of(buttons[0]))
                    continue

                # Verification redirects to the homepage, losing the channel URL.
                if urlsplit(driver.current_url).path.rstrip("/") != target_path:
                    driver.get(target)
                    continue
                wait.until(
                    lambda current: any(
                        link.text.strip()
                        for link in current.find_elements(
                            By.CSS_SELECTOR, self._video_link_selector
                        )
                    )
                )
                return
        except (TimeoutException, WebDriverException) as error:
            raise UnavailableFeed(self.feed.url) from error
        raise UnavailableFeed(self.feed.url)

    async def _parse_page_items(self) -> list[Item]:
        soup = await self.get_soup(self._get_target_url())
        channel_tag = soup.select_one('[data-testid="video_channel_name"]')
        channel = channel_tag.get_text(" ", strip=True) if channel_tag else self.feed.title
        items: list[Item] = []
        links: set[str] = set()
        for card in soup.select(self._video_selector):
            title_tag = card.select_one('[data-testid="video_card_title"] a')
            href = title_tag.get("href") if title_tag else None
            if not isinstance(href, str) or title_tag is None:
                continue
            path = urlsplit(urljoin(self.feed.url, href)).path
            if not path.startswith("/video"):
                continue
            link = urljoin("https://vkvideo.ru/", path)
            if link in links:
                continue
            links.add(link)
            items.append(
                Item(
                    title=f"VK Video: {channel}",
                    text=title_tag.get_text(" ", strip=True),
                    date=constant_datetime,
                    link=link,
                )
            )
            if len(items) == self._max_videos:
                break
        if not items:
            raise UnavailableFeed(self.feed.url)
        return items

    async def _generate_hash(self, item: Item) -> str:
        return HashService.hash_str(item.link)
