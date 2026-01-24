from dataclasses import dataclass
from typing import Callable

from selenium.webdriver.remote.webdriver import WebDriver


@dataclass
class SeleniumGetHtmlArgs:
    url: str
    should_delete_cookies: bool
    should_load_cookies: bool
    should_save_cookies: bool
    make_actions_function: Callable[[WebDriver], None] | None
    selenium_wait_timeout_seconds: int
