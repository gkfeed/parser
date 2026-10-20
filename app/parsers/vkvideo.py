from datetime import UTC, datetime
from typing import Any, ClassVar, override
from urllib.parse import urljoin, urlsplit, urlunsplit

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait
from yt_dlp.utils import DownloadError

from app.extensions.parsers.exceptions import FeedUnavailable
from app.extensions.parsers.hash import ItemLinkHashExtension
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.serializers.feed import Item
from app.services.ytdlp import BaseExtractionMode, YtdlpInfoExtractor
from app.utils.datetime import constant_datetime


class _InvalidVkVideoMetadata(ValueError):
    """The source returned metadata that cannot describe a video feed."""


def _video_link(video: dict[str, Any]) -> str:
    video_id = video.get("id")
    if video_id:
        if not isinstance(video_id, (str, int)) or isinstance(video_id, bool):
            raise _InvalidVkVideoMetadata(
                "VK Video extraction returned an invalid video ID"
            )
        if not str(video_id).strip():
            raise _InvalidVkVideoMetadata(
                "VK Video extraction returned a blank video ID"
            )
        return f"https://vkvideo.ru/video{video_id}"

    link = video.get("webpage_url") or video.get("url")
    if not isinstance(link, str) or not link.strip():
        raise _InvalidVkVideoMetadata(
            "VK Video extraction returned a video without a usable link"
        )
    return link


def _video_publication_date(video: dict[str, Any], link: str) -> datetime:
    timestamp = video.get("timestamp") or video.get("release_timestamp")
    upload_date = video.get("upload_date")
    try:
        if timestamp:
            return datetime.fromtimestamp(timestamp, UTC)
        if upload_date:
            return datetime.strptime(upload_date, "%Y%m%d").replace(tzinfo=UTC)
        return constant_datetime
    except (TypeError, ValueError, OverflowError, OSError) as error:
        raise ValueError(f"Invalid VK Video publication date for {link}") from error


def _validate_extraction(
    url: str, info: dict[str, Any] | None, error: str | None
) -> dict[str, Any]:
    if not isinstance(info, dict):
        raise _InvalidVkVideoMetadata("VK Video extraction did not return metadata")
    entries = info.get("entries")
    if not isinstance(entries, list):
        raise _InvalidVkVideoMetadata(
            "VK Video extraction did not return an entries list"
        )
    if not entries:
        # An empty extraction does not confirm that the channel has no videos.
        raise _InvalidVkVideoMetadata("VK Video extraction returned no videos")
    for video in entries:
        if not isinstance(video, dict) or not video:
            raise _InvalidVkVideoMetadata(
                "VK Video extraction returned an invalid video entry"
            )
        _video_link(video)
    return info


class VkVideoExtractionMode(BaseExtractionMode):
    result_handler = staticmethod(_validate_extraction)
    opts: ClassVar[dict[str, Any]] = {
        **BaseExtractionMode.opts,
        "extract_flat": False,
        "skip_download": True,
    }


class VkVideoFeed(ItemLinkHashExtension, SeleniumParserExtension):
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
            # Cached results bypass the extraction mode's result handler.
            info = _validate_extraction(self.feed.url, info, None)
        except (ValueError, DownloadError):
            return await self._parse_page_items()

        channel = info.get("title") or self.feed.title
        items = []
        for video in info["entries"]:
            link = _video_link(video)
            published_at = _video_publication_date(video, link)

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
        # Leave room to reopen the channel after the verification redirects.
        for _ in range(self._challenge_attempts + 2):
            try:
                ready = self._make_browser_attempt(driver, wait, target, target_path)
            except (TimeoutException, WebDriverException) as error:
                raise FeedUnavailable(self.feed.url, "browser_action_failed") from error
            if ready:
                return
        raise FeedUnavailable(self.feed.url, "browser_challenge")

    def _make_browser_attempt(
        self, driver: WebDriver, wait: WebDriverWait, target: str, target_path: str
    ) -> bool:
        wait.until(
            ec.presence_of_element_located(
                (By.CSS_SELECTOR, f"button.start, {self._video_link_selector}")
            )
        )
        buttons = driver.find_elements(By.CSS_SELECTOR, "button.start")
        if buttons:
            wait.until(ec.element_to_be_clickable(buttons[0])).click()
            wait.until(ec.staleness_of(buttons[0]))
            return False

        # Verification redirects to the homepage, losing the channel URL.
        if urlsplit(driver.current_url).path.rstrip("/") != target_path:
            driver.get(target)
            return False
        wait.until(
            lambda current: any(
                link.text.strip()
                for link in current.find_elements(
                    By.CSS_SELECTOR, self._video_link_selector
                )
            )
        )
        return True

    async def _parse_page_items(self) -> list[Item]:
        try:
            soup = await self.get_soup(self._get_target_url())
        except WebDriverException as error:
            raise FeedUnavailable(self.feed.url, "browser_load_failed") from error
        channel_tag = soup.select_one('[data-testid="video_channel_name"]')
        channel = (
            channel_tag.get_text(" ", strip=True) if channel_tag else self.feed.title
        )
        items: list[Item] = []
        links: set[str] = set()
        for card in soup.select(self._video_selector):
            title_tag = card.select_one('[data-testid="video_card_title"] a')
            if title_tag is None:
                raise FeedUnavailable(self.feed.url, "video_card_missing_title_link")
            href = title_tag.get("href")
            if not isinstance(href, str) or not href.strip():
                raise FeedUnavailable(self.feed.url, "video_card_missing_href")
            path = urlsplit(urljoin(self.feed.url, href)).path
            if not path.startswith("/video"):
                continue
            link = urljoin("https://vkvideo.ru/", path)
            if link in links:
                continue
            title = title_tag.get_text(" ", strip=True)
            if not title:
                raise FeedUnavailable(self.feed.url, "video_card_missing_title")
            links.add(link)
            items.append(
                Item(
                    title=f"VK Video: {channel}",
                    text=title,
                    date=constant_datetime,
                    link=link,
                )
            )
            if len(items) == self._max_videos:
                break
        if not items:
            raise FeedUnavailable(self.feed.url, "missing_content")
        return items
