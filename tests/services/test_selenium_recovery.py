import asyncio
import os
import subprocess
from dataclasses import replace
from time import monotonic

import pytest
import requests
from selenium import webdriver
from selenium.webdriver.remote.client_config import ClientConfig

from app.services.container import Container
from app.services.selenium import SeleniumGetHtmlArgs, SeleniumService
from app.utils.selenium import GridWebDriver

pytestmark = pytest.mark.integration


@pytest.fixture
def isolated_grid():
    url = os.getenv("SELENIUM_TEST_GRID_URL")
    container = os.getenv("SELENIUM_TEST_CHROME_CONTAINER")
    if not url or not container or not os.getenv("SELENIUM_RECOVERY_REQUEST_PATH"):
        # These tests must run against an isolated Grid with its recovery watchdog.
        pytest.skip()
    return url, container


def new_driver(url: str) -> GridWebDriver:
    return GridWebDriver(
        url,
        options=webdriver.ChromeOptions(),
        client_config=ClientConfig(
            remote_server_addr=url,
            timeout=60,
            init_args_for_pool_manager={"init_args_for_pool_manager": {"retries": 0}},
        ),
    )


def stop_driver(container: str) -> None:
    subprocess.run(
        ["docker", "exec", container, "pkill", "-STOP", "-x", "chromedriver"],
        check=True,
    )


def test_hung_driver_cleanup_releases_grid(isolated_grid):
    url, container = isolated_grid
    driver = new_driver(url)
    stop_driver(container)
    started = monotonic()
    driver.quit()

    assert monotonic() - started < 45
    assert requests.get(f"{url}/status", timeout=5).json()["value"]["ready"]
    next_driver = new_driver(url)
    try:
        next_driver.get("data:text/html,<h1>Recovered</h1>")
        assert "Recovered" in next_driver.page_source
    finally:
        next_driver.quit()


async def test_cleanup_preserves_parser_error(isolated_grid):
    url, container = isolated_grid
    driver = new_driver(url)
    original_data = Container.get_data()
    Container.setup(replace(original_data, selenium_web_driver=lambda: driver))
    parsing_error = RuntimeError("The parser failed before cleanup")

    def fail_parser(_driver):
        stop_driver(container)
        raise parsing_error

    try:
        with pytest.raises(RuntimeError) as raised:
            await SeleniumService.get_html(
                SeleniumGetHtmlArgs(
                    url="data:text/html,<h1>Parser</h1>",
                    should_delete_cookies=False,
                    should_load_cookies=False,
                    should_save_cookies=False,
                    make_actions_function=fail_parser,
                    selenium_wait_timeout_seconds=0,
                )
            )
        assert raised.value is parsing_error
        response = await asyncio.to_thread(requests.get, f"{url}/status", timeout=5)
        assert response.json()["value"]["ready"]
    finally:
        Container.setup(original_data)
