import asyncio
from contextlib import ExitStack, suppress
from pathlib import Path

import pytest
import requests
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

from tests.browser.resources import LocalChromium, local_site
from tests.browser.source import SourceFailure, source

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    ("body", "failure"),
    [
        ('<div id="ready">Loaded</div>', None),
        ('<div id="error">Failed</div>', SourceFailure),
        ("", TimeoutException),
    ],
)
async def test_parser_reuse_after_success_error_or_timeout(
    site, browser, body, failure
):
    parser = source(site.publish(body), browser)
    if failure is None:
        assert [item.title for item in await parser.items] == ["Loaded"]
    else:
        with pytest.raises(failure):
            await parser.items
    browser.assert_released()
    with pytest.raises(RuntimeError, match="Browser actions are not active"):
        _ = parser.driver

    site.publish('<div id="ready">Loaded</div>')
    assert [item.title for item in await parser.items] == ["Loaded"]

    assert len(browser.drivers) == 2
    assert site.requests.count("/") == 2
    browser.assert_released()
    with pytest.raises(RuntimeError, match="Browser actions are not active"):
        _ = parser.driver


async def test_cancellation_releases_browser_and_parser_can_run_again(site, browser):
    parser = source(site.publish('<div id="ready">Loaded</div>'), browser)
    parser._selenium_wait_time = 60
    task = asyncio.create_task(parser.items)
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
    assert [item.title for item in await parser.items] == ["Loaded"]
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
