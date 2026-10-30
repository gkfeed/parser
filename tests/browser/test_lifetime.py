import asyncio
from contextlib import ExitStack, suppress
from pathlib import Path

import pytest
import requests
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By

from app.services.selenium import SeleniumGetHtmlArgs, SeleniumService
from tests.browser.resources import LocalChromium, local_site
from tests.browser.stories import media, stories_parser

pytestmark = pytest.mark.integration


async def test_cancellation_releases_browser_and_parser_can_run_again(site, browser):
    url = site.publish(media(site.url))
    parser = stories_parser(url, browser)
    parser._selenium_wait_time = 60
    task = asyncio.create_task(parser.get_html(url))
    try:
        # get_html yields after navigation, during its configured wait.
        await asyncio.sleep(0)
        assert browser.drivers
        assert "/" in site.requests
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    browser.assert_released()

    parser._selenium_wait_time = 0
    parser._results_wait_time = 4
    assert b"download-btn" in await parser.get_html(url)
    assert len(browser.drivers) == 2
    browser.assert_released()


@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_resource_scope_closes_server_and_browser_on_failure(failure):
    with pytest.raises(failure), ExitStack() as resources:
        site = resources.enter_context(local_site())
        browser = LocalChromium(resources)
        driver = browser()
        driver.get(site.publish('<div id="ready">Loaded</div>'))
        assert driver.find_element(By.ID, "ready").text == "Loaded"
        raise failure("Scenario interrupted")

    browser.assert_released()
    assert not Path(driver.capabilities["chrome"]["userDataDir"]).exists()
    with pytest.raises(requests.ConnectionError):
        await asyncio.to_thread(requests.get, site.url, timeout=1)


async def test_explicit_local_factory_never_falls_back_to_an_external_worker(browser):
    with local_site() as site:
        url = site.url
    # A closed loopback server produces a real browser navigation failure.
    args = SeleniumGetHtmlArgs(
        url=url,
        should_delete_cookies=False,
        should_load_cookies=False,
        should_save_cookies=False,
        make_actions_function=None,
        selenium_wait_timeout_seconds=0,
    )

    with pytest.raises(WebDriverException, match="ERR_CONNECTION_REFUSED"):
        await SeleniumService.get_html(
            args, fallback_to_external_selenium=True, driver_factory=browser
        )

    browser.assert_released()
