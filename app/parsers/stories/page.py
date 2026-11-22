from collections.abc import Callable
from typing import Literal, Never

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app.extensions.parsers.exceptions import FeedUnavailable
from app.services.selenium.diagnostics import BrowserDiagnostics, BrowserSnapshot
from app.services.selenium.lazy_list import (
    LazyListLoader,
    LazyListTimeoutError,
    LazyListUnavailableError,
)

from .errors import classify_error, failure_reason, http_error_status, unavailable


class StoriesPage:
    """Interact with the Stories page using a driver owned by SeleniumService."""

    _results_wait_time = 30

    def __init__(self, driver: WebDriver, feed_url: str) -> None:
        self.driver = driver
        self.feed_url = feed_url
        self._user_name = feed_url.split("/")[-1]
        self.diagnostics = BrowserDiagnostics(driver)

    def _click_element(self, element: WebElement) -> None:
        try:
            self.driver.execute_script("arguments[0].click();", element)
        except TimeoutException:
            # Background requests can outlive an otherwise usable result page.
            pass

    def run(self) -> None:
        # The results page keeps some requests open in Docker, so a synchronous
        # click can otherwise wait for Selenium's five-minute default timeout.
        self.driver.set_page_load_timeout(30)

        dismiss_buttons = self.driver.find_elements(
            By.XPATH,
            "/html/body/div/div[2]/div[2]/div[3]/div[2]/button[1]",
        )
        if dismiss_buttons:
            self._click_element(dismiss_buttons[0])

        links = self._wait_for(
            "search_form",
            EC.visibility_of_any_elements_located(
                (By.CSS_SELECTOR, "form.search-form input.search-form__input")
            ),
        )
        self.driver.execute_script(
            """
            arguments[0].value = arguments[1];
            arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
            """,
            links[0],
            self._user_name,
        )

        button = self._wait_for(
            "search_submit",
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "form.search-form .search-form__button")
            ),
        )
        self._click_element(button)

        stories_button = (
            "//button[contains(@class, 'tabs-component__button') "
            "and normalize-space(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            "'abcdefghijklmnopqrstuvwxyz')) = 'stories']"
        )
        result = self._wait_for(
            "search_result",
            EC.any_of(
                EC.presence_of_element_located((By.XPATH, stories_button)),
                self._loaded_error,
            ),
        )
        result_classes = (result.get_attribute("class") or "").split()
        if "error-message__text" in result_classes:
            self._check_error(result, "search_result")
        if (
            "tabs-component__button--disabled" in result_classes
            or not result.is_enabled()
            or result.get_attribute("aria-disabled") == "true"
        ):
            raise self._browser_unavailable(
                "stories_tab", reason="stories_tab_disabled"
            )
        self._click_element(result)
        media_ready = EC.all_of(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    stories_button
                    + "[contains(@class, 'tabs-component__button--active')]",
                )
            ),
            # The subscription landing hides results while requests still run.
            # A hidden loader is not evidence that loading has finished.
            EC.none_of(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".search-result .loader-component")
                )
            ),
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    ".search-result .profile-media-list__item a.download-btn[href]",
                )
            ),
        )
        stories_result = self._wait_for(
            "stories_media", EC.any_of(self._loaded_error, media_ready)
        )
        if isinstance(stories_result, WebElement):
            self._check_error(stories_result, "stories_media")

        self._dismiss_subscription_landing()
        self._load_all_media()

    def _dismiss_subscription_landing(self) -> None:
        buttons = self.driver.find_elements(
            By.CSS_SELECTOR, ".tz-landing-exp .tz-landing__button-close"
        )
        if not buttons:
            return

        # Anonyig hides loaded results behind its subscription landing. Use its
        # browser-download button so pagination can inspect the visible list.
        self._click_element(buttons[0])
        self._wait_for(
            "subscription_landing",
            EC.none_of(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".tz-landing-exp"))
            ),
        )

    def _load_all_media(self) -> None:
        try:
            LazyListLoader(
                self.driver,
                items_selector=".search-result .profile-media-list__item",
                trigger_selector=".search-result .profile-media-list .trigger",
            ).load(self._results_wait_time)
        except LazyListUnavailableError as exc:
            raise self._browser_unavailable(
                "pagination", reason="media_loading_unverified"
            ) from exc
        except LazyListTimeoutError as exc:
            raise self._browser_unavailable(
                "pagination", reason="media_loading_timeout"
            ) from exc

    @staticmethod
    def _loaded_error(driver: WebDriver) -> WebElement | Literal[False]:
        if driver.find_elements(By.CSS_SELECTOR, ".search-result .loader-component"):
            return False
        # Anonyig's subscription landing can hide the whole search result.
        # Read the actual error text, excluding the fallback popup's ad copy.
        for error in driver.find_elements(
            By.CSS_SELECTOR, ".search-result .error-message__text"
        ):
            if (error.get_attribute("textContent") or "").strip():
                return error
        return False

    def _wait_for[T](
        self,
        stage: str,
        condition: Callable[[WebDriver], T | Literal[False]],
    ) -> T:
        try:
            return WebDriverWait(self.driver, self._results_wait_time).until(condition)
        except TimeoutException as exc:
            raise self._browser_unavailable(stage, reason=f"{stage}_timeout") from exc

    def _check_error(self, error: WebElement, stage: str) -> Never:
        raise self._browser_unavailable(
            stage, message=error.get_attribute("textContent") or ""
        )

    def _browser_context(self) -> BrowserSnapshot:
        return self.diagnostics.capture(
            """
            const count = s => document.querySelectorAll(s).length;
            const triggers = [...document.querySelectorAll(
                '.search-result .profile-media-list .trigger')];
            const forms = count('form.search-form');
            const results = count('.search-result');
            return {
                document_status: performance.getEntriesByType('navigation')[0]?.responseStatus || null,
                search_forms: forms,
                search_results: results,
                loaders: count('.search-result .loader-component'),
                media_cards: count('.search-result .profile-media-list__item'),
                download_links: count('.search-result a.download-btn[href]'),
                subscription_landings: count('.tz-landing-exp'),
                pagination_triggers: triggers.length,
                visible_pagination_triggers: triggers.filter(e =>
                    e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})).length,
                full_page_error: !forms && !results,
                text: document.querySelector(
                    '.search-result .error-message__text')?.textContent ||
                    (!forms && !results ?
                        document.title + ' ' + (document.body?.innerText || '') : '')
            };
            """
        )

    def _browser_unavailable(
        self, stage: str, *, reason: str | None = None, message: str = ""
    ) -> FeedUnavailable:
        snapshot = self._browser_context()
        message = message or snapshot.text
        error_kind = classify_error(message) if message else None
        reason = failure_reason(
            reason,
            error_kind=error_kind,
            document_status=snapshot.fields.get("document_status"),
            full_page_error=bool(snapshot.fields.get("full_page_error")),
        )
        self.diagnostics.log(
            "stories_source_unavailable",
            stage,
            snapshot,
            message=message,
            reason=reason,
            error_kind=error_kind,
            error_http_status=http_error_status(message),
        )
        return unavailable(self.feed_url, reason)
