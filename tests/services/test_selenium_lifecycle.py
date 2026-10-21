import os

import pytest
import requests

from app.utils.selenium import cleanup_grid
from tests.services.test_selenium_recovery import new_driver, stop_driver

pytestmark = pytest.mark.integration


@pytest.fixture
def isolated_grid():
    url = os.getenv("SELENIUM_TEST_GRID_URL")
    container = os.getenv("SELENIUM_TEST_CHROME_CONTAINER")
    if not url or not container or not os.getenv("SELENIUM_RECOVERY_REQUEST_PATH"):
        pytest.skip()
    return url, container


@pytest.mark.parametrize("hung", [False, True])
def test_startup_releases_previous_workers_browser(isolated_grid, hung):
    url, container = isolated_grid
    previous_driver = new_driver(url)
    try:
        previous_driver.get("data:text/html,<h1>Previous worker</h1>")
        if hung:
            stop_driver(container)
        cleanup_grid(url)
        assert requests.get(f"{url}/status", timeout=5).json()["value"]["ready"]

        driver = new_driver(url)
        try:
            driver.get("data:text/html,<h1>Next worker</h1>")
            assert "Next worker" in driver.page_source
        finally:
            driver.quit()
    finally:
        previous_driver.quit()
