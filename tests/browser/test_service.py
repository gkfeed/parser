import pytest
from selenium.common.exceptions import WebDriverException

from app.services.selenium import SeleniumGetHtmlArgs, SeleniumService
from tests.browser.resources import local_site

pytestmark = pytest.mark.integration


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
