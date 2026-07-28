from typing import override
from urllib.parse import urljoin

from bs4 import Tag
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait

from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.extensions.parsers.selenium import SeleniumParserExtension


class RTLSeriesFeed(PostToItemsMixin, SeleniumParserExtension):
    _base_url = "https://plus.rtl.de"

    @override
    def make_actions(self, driver: WebDriver) -> None:
        # RTL rejects the anonymous session created with the shared spoofed
        # user agent, so reload with the running browser's real version.
        browser_version = driver.capabilities["browserVersion"]
        driver.execute_cdp_cmd(
            "Network.setUserAgentOverride",
            {
                "userAgent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    f"HeadlessChrome/{browser_version} Safari/537.36"
                )
            },
        )
        driver.delete_all_cookies()
        driver.execute_script("localStorage.clear(); sessionStorage.clear()")
        driver.refresh()

        WebDriverWait(driver, 15).until(
            lambda current_driver: current_driver.find_elements(
                By.CSS_SELECTOR,
                (
                    'article:not(:has([aria-label="Blockierter Inhalt"])) '
                    'a[href*="/video/"]'
                ),
            )
        )

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)
        return [
            link
            for link in soup.find_all("a", href=True)
            if isinstance(link, Tag) and self._is_free_episode_link(link)
        ]

    @staticmethod
    def _is_free_episode_link(link: Tag) -> bool:
        card = link.find_parent("article")
        is_locked = isinstance(card, Tag) and card.find(
            attrs={"aria-label": "Blockierter Inhalt"}
        )
        return (
            "/video/" in str(link["href"])
            and link.find("p") is not None
            and not is_locked
        )

    @override
    async def _get_post_title(self, post: Tag) -> str:
        paragraphs = post.find_all("p")
        if paragraphs:
            return paragraphs[-1].get_text(" ", strip=True)
        raise ValueError("Episode link does not contain a title")

    @override
    async def _get_post_link(self, post: Tag) -> str:
        href = post.get("href")
        if isinstance(href, str):
            return urljoin(self._base_url, href)
        raise ValueError("Link element does not contain a valid href")
