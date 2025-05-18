from dataclasses import dataclass, asdict
from typing import Callable, Any
import time
import pickle
import os

from selenium.webdriver.remote.webdriver import WebDriver

from app.settings import SELENIUM_COOKIES_PATH

import app.configs
from app.utils.inject import inject
from . import worker_sync


@dataclass
class SeleniumGetHtmlArgs:
    url: str
    should_delete_cookies: bool
    should_load_cookies: bool
    should_save_cookies: bool
    make_actions_function: Callable[[WebDriver], None]
    selenium_wait_timeout_seconds: int


@worker_sync
async def get_html(args: SeleniumGetHtmlArgs) -> str:
    return await _get_html(**asdict(args))


@inject({"driver": "selenium_web_driver"}, call=True)
async def _get_html(
    url: str,
    driver: WebDriver,
    should_delete_cookies: bool,
    should_load_cookies: bool,
    should_save_cookies: bool,
    make_actions_function: Callable[[WebDriver], None],
    selenium_wait_timeout_seconds: int,
) -> str:
    try:
        if should_delete_cookies:
            driver.delete_all_cookies()

        if should_load_cookies:
            driver.get(url)
            driver.delete_all_cookies()
            for cookie in _load_cookies():
                driver.add_cookie(cookie)

        driver.get(url)
        time.sleep(selenium_wait_timeout_seconds)

        make_actions_function(driver)

        html = driver.page_source

        if should_save_cookies:
            pickle.dump(driver.get_cookies(), open(SELENIUM_COOKIES_PATH, "wb"))

        driver.close()
        driver.quit()
        return html
    except Exception as e:
        driver.close()
        driver.quit()
        raise e


def _load_cookies():
    if not os.path.isfile(SELENIUM_COOKIES_PATH):
        return []
    return pickle.load(open(SELENIUM_COOKIES_PATH, "rb"))
