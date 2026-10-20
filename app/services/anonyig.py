from dataclasses import dataclass, field
from typing import Literal

import structlog
from bs4 import BeautifulSoup, Tag
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app.services.selenium import SeleniumGetHtmlArgs, SeleniumService
from app.services.selenium.lazy_list import (
    LazyListLoader,
    LazyListTimeoutError,
    LazyListUnavailableError,
)

logger = structlog.get_logger(__name__)

ANONYIG_URL = "https://anonyig.com/en/iganony/"


class AnonyigError(Exception):
    """An unusable source response, without feed or retry policy."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class AnonyigOptions:
    results_wait_seconds: int = 30
    page_load_timeout_seconds: int = 30
    selenium_wait_seconds: int = 0
    pagination_settle_seconds: float = 2
    max_media_items: int | None = None
    should_delete_cookies: bool = True
    should_load_cookies: bool = False
    should_save_cookies: bool = False
    # This ad player creates/detaches nested frames that can hang ChromeDriver.
    blocked_url_patterns: tuple[str, ...] = ("*://player.avplayer.com/*",)


@dataclass(frozen=True)
class AnonyigClient:
    username: str
    media_kind: Literal["posts", "stories"]
    options: AnonyigOptions = field(default_factory=AnonyigOptions)

    async def get_html(self, url: str = ANONYIG_URL) -> bytes:
        try:
            html = await SeleniumService.get_html(
                SeleniumGetHtmlArgs(
                    url=url,
                    should_delete_cookies=self.options.should_delete_cookies,
                    should_load_cookies=self.options.should_load_cookies,
                    should_save_cookies=self.options.should_save_cookies,
                    make_actions_function=self.make_actions,
                    selenium_wait_timeout_seconds=self.options.selenium_wait_seconds,
                    page_load_timeout_seconds=self.options.page_load_timeout_seconds,
                    blocked_url_patterns=self.options.blocked_url_patterns,
                )
            )
        except TimeoutException as exc:
            raise AnonyigError("page_timeout") from exc
        except WebDriverException as exc:
            raise AnonyigError("browser_error") from exc
        self.validate_html(html)
        return html.encode()

    def validate_html(self, html: str | bytes) -> None:
        result = BeautifulSoup(html, "html.parser").select_one(".search-result")
        if not isinstance(result, Tag):
            reason = (
                "missing_search_result"
                if self.media_kind == "posts"
                else "media_response_invalid"
            )
            raise AnonyigError(reason)
        if result.select_one(".loader-component") is not None:
            raise AnonyigError("media_loading_unverified")
        error = result.select_one(".error-message__text")
        if error is None and self.media_kind == "posts":
            error = result.select_one(".error-message")
        if isinstance(error, Tag) and error.get_text(strip=True):
            self._check_error(error.get_text(" ", strip=True))
            if result.select_one(".profile-media-list__item") is not None:
                raise ValueError(
                    "Anonyig response contains both media and an empty result"
                )
            return
        if self.media_kind == "stories":
            active_tab = result.select_one(".tabs-component__button--active")
            if not isinstance(active_tab, Tag):
                raise AnonyigError("media_response_invalid")
            if active_tab.get_text(strip=True).lower() != "stories":
                raise AnonyigError("media_response_invalid")
        if not result.select(".profile-media-list__item"):
            raise AnonyigError("empty_unverified")

    def make_actions(self, driver: WebDriver) -> None:
        # Results can keep requests open, so clicks need a bounded page timeout.
        driver.set_page_load_timeout(self.options.page_load_timeout_seconds)
        self._dismiss_consent(driver)
        wait = WebDriverWait(driver, self.options.results_wait_seconds)
        self._submit_search(driver, wait)
        if self.media_kind == "stories":
            self._select_stories(driver, wait)
        if not self._wait_for_media(wait):
            return
        self._show_results(driver)
        self._load_all_media(driver)

    def _dismiss_consent(self, driver: WebDriver) -> None:
        for by, selector in (
            (By.CSS_SELECTOR, ".fc-cta-do-not-consent"),
            (By.XPATH, "/html/body/div/div[2]/div[2]/div[3]/div[2]/button[1]"),
        ):
            buttons = driver.find_elements(by, selector)
            if buttons:
                self._click(driver, buttons[0])

    def _submit_search(self, driver: WebDriver, wait: WebDriverWait[WebDriver]) -> None:
        inputs = wait.until(
            EC.visibility_of_any_elements_located(
                (By.CSS_SELECTOR, "form.search-form input.search-form__input")
            )
        )
        driver.execute_script(
            "arguments[0].value = arguments[1];"
            "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
            inputs[0],
            self.username,
        )
        button = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "form.search-form .search-form__button")
            )
        )
        self._click(driver, button)

    @property
    def _stories_button(self) -> str:
        return (
            "//button[contains(@class, 'tabs-component__button') "
            "and normalize-space(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            "'abcdefghijklmnopqrstuvwxyz')) = 'stories']"
        )

    def _select_stories(
        self, driver: WebDriver, wait: WebDriverWait[WebDriver]
    ) -> None:
        result = wait.until(
            EC.any_of(
                EC.presence_of_element_located((By.XPATH, self._stories_button)),
                self._loaded_error,
            )
        )
        classes = (result.get_attribute("class") or "").split()
        if "error-message__text" in classes:
            self._check_error(result.get_attribute("textContent") or "")
        if (
            "tabs-component__button--disabled" in classes
            or not result.is_enabled()
            or result.get_attribute("aria-disabled") == "true"
        ):
            raise AnonyigError("private")
        self._click(driver, result)

    def _wait_for_media(self, wait: WebDriverWait[WebDriver]) -> bool:
        media_selector = ".search-result .profile-media-list__item"
        if self.media_kind == "stories":
            media_selector += " a.download-btn[href]"
        conditions = [
            # Hidden loaders still mean the source request has not finished.
            EC.none_of(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".search-result .loader-component")
                )
            ),
            EC.presence_of_element_located((By.CSS_SELECTOR, media_selector)),
        ]
        if self.media_kind == "stories":
            conditions.append(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        self._stories_button
                        + "[contains(@class, 'tabs-component__button--active')]",
                    )
                )
            )
        result = wait.until(EC.any_of(self._loaded_error, EC.all_of(*conditions)))
        if isinstance(result, WebElement):
            self._check_error(result.get_attribute("textContent") or "")
            return False
        return True

    def _loaded_error(self, driver: WebDriver) -> WebElement | Literal[False]:
        if driver.find_elements(By.CSS_SELECTOR, ".search-result .loader-component"):
            return False
        # The subscription landing hides results. Exclude popup advertising copy.
        for error in driver.find_elements(
            By.CSS_SELECTOR, ".search-result .error-message__text"
        ):
            if (error.get_attribute("textContent") or "").strip():
                return error
        if self.media_kind == "stories":
            return False
        for error in driver.find_elements(
            By.CSS_SELECTOR, ".search-result .error-message"
        ):
            if (error.get_attribute("textContent") or "").strip():
                return error
        return False

    def _check_error(self, message: str) -> None:
        message = " ".join(message.lower().split())
        if self.media_kind == "posts" and message.rstrip(".! ") in (
            "no posts",
            "no posts found",
            "no publications found",
        ):
            logger.info("anonyig_posts_empty")
            return
        if self.media_kind == "stories" and "no stories" in message:
            # Anonyig also uses this message for upstream failures.
            logger.warning("stories_empty_unverified")
            raise AnonyigError("empty_unverified")
        if "private" in message:
            raise AnonyigError("private")
        if any(
            text in message
            for text in ("user not found", "profile not found", "account not found")
        ):
            raise AnonyigError("not_found")
        raise AnonyigError("upstream_error")

    @staticmethod
    def _show_results(driver: WebDriver) -> None:
        result = driver.find_element(By.CSS_SELECTOR, ".search-result")
        if result.is_displayed():
            return
        # Reveal the landing experiment so its IntersectionObserver can run.
        driver.execute_script(
            "arguments[0].style.setProperty('display', 'block', 'important');"
            "arguments[0].style.setProperty('visibility', 'visible', 'important');",
            result,
        )

    def _load_all_media(self, driver: WebDriver) -> None:
        try:
            LazyListLoader(
                driver,
                items_selector=".search-result .profile-media-list__item",
                trigger_selector=".search-result .profile-media-list .trigger",
                settle_seconds=self.options.pagination_settle_seconds,
                trigger_removed_on_completion=self.media_kind == "posts",
            ).load(
                self.options.results_wait_seconds,
                max_items=self.options.max_media_items,
            )
        except LazyListUnavailableError as exc:
            raise AnonyigError("media_loading_unverified") from exc
        except LazyListTimeoutError as exc:
            raise AnonyigError("media_loading_timeout") from exc

    @staticmethod
    def _click(driver: WebDriver, element: WebElement) -> None:
        try:
            driver.execute_script("arguments[0].click();", element)
        except TimeoutException:
            # Background requests can outlive a usable page. The next wait must
            # still verify a completed result before get_html can succeed.
            pass
