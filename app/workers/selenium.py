import asyncio
import contextlib
import os
import pickle
from collections.abc import Callable
from dataclasses import asdict

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.remote.webdriver import WebDriver

import app.configs  # noqa: F401
from app.configs.selenium import SELENIUM_COOKIES_PATH
from app.services.selenium.schemas import SeleniumGetHtmlArgs
from app.utils.inject import inject


async def get_html(args: SeleniumGetHtmlArgs) -> str:
    return await _get_html(**asdict(args))


@inject({"driver": "selenium_web_driver"}, call=True)
async def _get_html(
    url: str,
    driver: WebDriver,
    should_delete_cookies: bool,
    should_load_cookies: bool,
    should_save_cookies: bool,
    make_actions_function: Callable[[WebDriver], None] | None,
    selenium_wait_timeout_seconds: int,
    page_load_timeout_seconds: int | None,
) -> str:
    try:
        if page_load_timeout_seconds is not None:
            driver.set_page_load_timeout(page_load_timeout_seconds)

        if should_delete_cookies:
            driver.delete_all_cookies()

        if should_load_cookies:
            driver.get(url)
            driver.delete_all_cookies()
            for cookie in _load_cookies():
                driver.add_cookie(cookie)

        try:
            driver.get(url)
        except TimeoutException:
            if page_load_timeout_seconds is None:
                raise
        await asyncio.sleep(selenium_wait_timeout_seconds)

        if make_actions_function:
            make_actions_function(driver)

        html = driver.page_source

        if should_save_cookies:
            await asyncio.to_thread(_save_cookies, driver.get_cookies())

    except BaseException:
        # Preserve the original parsing/cancellation error if session cleanup also
        # fails. Calling close() first can prevent quit() from ever reaching the
        # remote Selenium server, leaving its temporary Chrome profile behind.
        with contextlib.suppress(Exception):
            driver.quit()
        raise

    driver.quit()
    return html


def _load_cookies():
    if not os.path.isfile(SELENIUM_COOKIES_PATH):
        return []
    with open(SELENIUM_COOKIES_PATH, "rb") as cookies_file:
        return pickle.load(cookies_file)


def _save_cookies(cookies) -> None:
    with open(SELENIUM_COOKIES_PATH, "wb") as cookies_file:
        pickle.dump(cookies, cookies_file)
