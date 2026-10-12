import os
from pathlib import Path
from urllib.parse import quote

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.client_config import ClientConfig

from app.extensions.parsers.exceptions import FeedUnavailable
from app.parsers.stories import InstagramStoriesFeed
from app.serializers.feed import Feed

pytestmark = pytest.mark.integration


@pytest.fixture
def stories_browser():
    """Use an isolated Grid supplied through STORIES_SELENIUM_TEST_URL."""
    url = os.environ.get("STORIES_SELENIUM_TEST_URL")
    if not url:
        pytest.skip()
    driver = webdriver.Remote(
        url,
        options=webdriver.ChromeOptions(),
        client_config=ClientConfig(remote_server_addr=url, timeout=60),
    )
    try:
        yield driver
    finally:
        driver.quit()


@pytest.mark.parametrize(
    ("scenario", "reason"),
    [
        ("upstream", "upstream_error"),
        ("not_found", "not_found"),
        ("private", "private"),
        ("empty", None),
        ("media", None),
    ],
)
def test_stories_results_under_subscription_landing(stories_browser, scenario, reason):
    fixture = (
        Path(__file__).parents[1] / "fixtures/stories/subscription-landing.html"
    ).read_text()
    stories_browser.get(
        "data:text/html;charset=utf-8," + quote(fixture) + "#" + scenario
    )
    parser = InstagramStoriesFeed(
        Feed(
            id=1,
            title="stories",
            type="stories",
            url="https://www.instagram.com/example",
        ),
        {},
    )

    if reason:
        with pytest.raises(FeedUnavailable) as exc:
            parser.make_actions(stories_browser)
        assert exc.value.reason == reason
        assert exc.value.retry_at is not None
    else:
        parser.make_actions(stories_browser)
        assert (
            stories_browser.find_element(By.ID, "app").get_attribute("data-finished")
            == "stories"
        )

    assert (
        stories_browser.find_element(By.ID, "app").get_attribute("data-query")
        == "example"
    )
    if scenario == "media":
        assert (
            stories_browser.find_element(
                By.CSS_SELECTOR, "a.download-btn"
            ).get_attribute("href")
            == "https://media.example/story.mp4"
        )
