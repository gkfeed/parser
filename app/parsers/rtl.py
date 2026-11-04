import json
import re
from typing import override
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait

from app.extensions.parsers.exceptions import FeedUnavailable
from app.extensions.parsers.hash import ItemIdentityHashExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.utils.html import require_tag, required_attr, required_text


class RTLSeriesFeed(
    PostToItemsMixin, ItemIdentityHashExtension, SeleniumParserExtension
):
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

        try:
            WebDriverWait(driver, 15).until(self._page_is_ready)
        except TimeoutException as exc:
            raise FeedUnavailable(self.feed.url, "rtl_catalog_timeout") from exc

    def _page_is_ready(self, driver: WebDriver) -> bool:
        try:
            self._validate_html(self.feed.url, driver.page_source.encode())
        except (FeedUnavailable, ValueError):
            return False
        return True

    @override
    def _validate_html(self, url: str, html: bytes) -> None:
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(strip=True).lower() if soup.title else ""
        if title.startswith("just a moment") or soup.select_one(
            "#challenge-form, #challenge-running, #cf-error-details"
        ):
            raise FeedUnavailable(url, "rtl_challenge_or_error")

        require_tag(soup.find("main"), "RTL main content")
        required_text(
            require_tag(soup.find("h1"), "RTL series title"), "RTL series title"
        )
        links = self._episode_links(soup)
        if not links:
            self._validate_empty_catalog(soup)
            return

        for link in links:
            if self._is_locked(link):
                continue
            self._episode_title(link)
            self._episode_url(link)

    @staticmethod
    def _validate_empty_catalog(soup: BeautifulSoup) -> None:
        # The server embeds the season catalogue and its pagination in Redux.
        # A missing card list alone is not evidence of an empty catalogue.
        script = require_tag(
            soup.find("script", string=re.compile(r"root\.__dehydratedState =")),
            "RTL catalogue state",
        )
        serialized = script.get_text().split("root.__dehydratedState =", 1)[1]
        try:
            dehydrated = json.JSONDecoder().raw_decode(serialized.lstrip())[0]
            state = json.loads(dehydrated["__reduxState"])
            layout = state["layout"]
            programs = layout["layouts"]["main"]["program"]
            if (
                layout["waiting"]
                or layout["errors"]
                or not isinstance(programs, dict)
                or len(programs) != 1
            ):
                raise ValueError("RTL catalogue state is not ready")
            program = next(iter(programs.values()))
            blocks = program["blocks"]
            catalogues = [
                block["content"]
                for block in blocks
                if block["analytics"]["tealium"]["from"]
                == "feature.videos_by_season_by_program"
            ]
            if not catalogues:
                raise ValueError("Missing RTL season catalogue")
            for catalogue in catalogues:
                RTLSeriesFeed._validate_empty_season(catalogue)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Invalid or unconfirmed empty RTL catalogue") from exc

    @staticmethod
    def _validate_empty_season(catalogue: object) -> None:
        if not isinstance(catalogue, dict):
            raise TypeError("Invalid RTL season catalogue")
        pagination = catalogue.get("pagination")
        if not isinstance(pagination, dict):
            raise TypeError("Missing RTL season pagination")
        if (
            catalogue.get("items") != []
            or pagination.get("totalItems") != 0
            or pagination.get("nextPage", "missing") is not None
        ):
            raise ValueError("RTL catalogue is not confirmed empty")

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)
        return [link for link in self._episode_links(soup) if not self._is_locked(link)]

    @classmethod
    def _episode_links(cls, soup: BeautifulSoup) -> list[Tag]:
        return [
            link
            for link in soup.select("article a[href]")
            if cls._is_episode_link(link)
        ]

    @classmethod
    def _is_episode_link(cls, link: Tag) -> bool:
        url = urlsplit(
            urljoin(cls._base_url, required_attr(link, "href", "RTL episode"))
        )
        return (
            url.scheme in {"http", "https"}
            and url.hostname == "plus.rtl.de"
            and "/video/" in url.path
        )

    @staticmethod
    def _is_locked(link: Tag) -> bool:
        card = link.find_parent("article")
        return (
            isinstance(card, Tag)
            and card.find(attrs={"aria-label": "Blockierter Inhalt"}) is not None
        )

    @staticmethod
    def _episode_title(post: Tag) -> str:
        paragraphs = post.find_all("p")
        if not paragraphs:
            raise ValueError("Episode link does not contain a title")
        return required_text(
            require_tag(paragraphs[-1], "RTL episode title"),
            "RTL episode title",
            separator=" ",
        )

    @classmethod
    def _episode_url(cls, post: Tag) -> str:
        if not cls._is_episode_link(post):
            raise ValueError("Invalid RTL episode link")
        href = required_attr(post, "href", "RTL episode")
        if not urlsplit(href).path.split("/video/", 1)[1].strip("/"):
            raise ValueError("RTL episode link does not contain an episode")
        return urljoin(cls._base_url, href)

    @override
    async def _get_post_title(self, post: Tag) -> str:
        return self._episode_title(post)

    @override
    async def _get_post_link(self, post: Tag) -> str:
        return self._episode_url(post)
