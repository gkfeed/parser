import time
from dataclasses import dataclass

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait


class LazyListUnavailableError(Exception):
    """The pagination trigger cannot be used to verify list completion."""


class LazyListTimeoutError(Exception):
    """The list did not advance or finish before its loading deadline."""


@dataclass(frozen=True)
class LazyListLoader:
    """Load a lazy list using its source's completion signal.

    By default a visible persistent trigger completes after a quiet interval.
    Sources that remove the trigger must opt in; a quiet interval then fails.
    """

    driver: WebDriver
    items_selector: str
    trigger_selector: str
    settle_seconds: float = 2
    trigger_removed_on_completion: bool = False

    def load(self, timeout_seconds: float, *, max_items: int | None = None) -> None:
        """Load the complete list, or stop once at least max_items are present.

        A batch may exceed the bound; callers must slice the resulting cards.
        Below the bound, the usual trigger/completion checks still apply.
        """
        if max_items is not None and max_items <= 0:
            raise ValueError("max_items must be positive")
        deadline = time.monotonic() + timeout_seconds
        while max_items is None or self._item_count() < max_items:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LazyListTimeoutError
            grew = self._load_next_batch(min(self.settle_seconds, remaining))
            if time.monotonic() >= deadline:
                raise LazyListTimeoutError
            if not grew:
                return

    def _load_next_batch(self, timeout_seconds: float) -> bool:
        trigger = self._trigger()
        if trigger is None:
            return False
        count = self._item_count()
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});",
            trigger,
        )
        try:
            # Persistent triggers finish by settling; other sources remove the
            # trigger. A stalled removable trigger is a failure, not completion.
            WebDriverWait(self.driver, timeout_seconds).until(
                lambda browser: self._batch_finished(count)
            )
        except TimeoutException as exc:
            if self._trigger() is None:
                return False
            if self.trigger_removed_on_completion:
                raise LazyListTimeoutError("Pagination did not advance") from exc
            return False
        return self._item_count() > count

    def _batch_finished(self, previous_count: int) -> bool:
        if self._item_count() > previous_count:
            return True
        return self.trigger_removed_on_completion and not self.driver.find_elements(
            By.CSS_SELECTOR, self.trigger_selector
        )

    def _trigger(self) -> WebElement | None:
        triggers = self.driver.find_elements(By.CSS_SELECTOR, self.trigger_selector)
        if not triggers and self.trigger_removed_on_completion:
            return None
        if len(triggers) != 1:
            raise LazyListUnavailableError("Expected exactly one pagination trigger")
        trigger = triggers[0]
        if not trigger.is_displayed():
            raise LazyListUnavailableError("Pagination trigger is hidden")
        return trigger

    def _item_count(self) -> int:
        return len(self.driver.find_elements(By.CSS_SELECTOR, self.items_selector))
