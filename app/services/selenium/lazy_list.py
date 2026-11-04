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
    """The list did not finish loading before its overall deadline."""


@dataclass(frozen=True)
class LazyListLoader:
    driver: WebDriver
    items_selector: str
    trigger_selector: str
    settle_seconds: float = 2

    def load(self, timeout_seconds: float) -> None:
        deadline = time.monotonic() + timeout_seconds
        while True:
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
        count = len(self.driver.find_elements(By.CSS_SELECTOR, self.items_selector))
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});",
            trigger,
        )
        try:
            # A persistent trigger signals completion by no longer adding cards.
            # This wait must exceed the source's observer debounce/render delay.
            WebDriverWait(self.driver, timeout_seconds).until(
                lambda browser: (
                    len(browser.find_elements(By.CSS_SELECTOR, self.items_selector))
                    > count
                )
            )
        except TimeoutException:
            self._trigger()
            return False
        return True

    def _trigger(self) -> WebElement:
        triggers = self.driver.find_elements(By.CSS_SELECTOR, self.trigger_selector)
        if len(triggers) != 1:
            raise LazyListUnavailableError("Expected exactly one pagination trigger")
        trigger = triggers[0]
        if not trigger.is_displayed():
            raise LazyListUnavailableError("Pagination trigger is hidden")
        return trigger
