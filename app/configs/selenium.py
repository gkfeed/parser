from pathlib import Path

from selenium import webdriver
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService

from app.utils.is_in_docker import IS_IN_DOCKER
from app.configs.env import SELENIUM_DOCKER_URL

SELENIUM_COOKIES_PATH = "/data/cookies.pkl"
IS_HEADLESS = True
FALLBACK_TO_EXTERNAL_SELENIUM = True
_CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/149.0.0.0 Safari/537.36"
)


def get_driver() -> WebDriver:
    if IS_IN_DOCKER:
        return _get_docker_driver()

    if not Path("/usr/bin/chromedriver").exists():
        raise ValueError("chromedriver (chromium) should be installed")

    if IS_HEADLESS:
        return _get_local_headless_chrome_driver()
    return _get_local_chrome_driver()


def _get_local_chrome_driver() -> WebDriver:
    return webdriver.Chrome(
        service=Service(executable_path="/usr/bin/chromedriver"),
        options=webdriver.ChromeOptions(),
    )


def _get_docker_driver() -> WebDriver:
    return webdriver.Remote(
        SELENIUM_DOCKER_URL,
        options=_get_chrome_options(),
    )


def _get_local_headless_chrome_driver() -> WebDriver:
    options = _get_chrome_options()
    options.add_argument("--headless")
    return webdriver.Chrome(
        service=Service(executable_path="/usr/bin/chromedriver"),
        options=options,
    )


def _get_chrome_options() -> webdriver.ChromeOptions:
    options = webdriver.ChromeOptions()
    # Chrome identifies itself as HeadlessChrome by default. Some sites, including
    # Rezka's Anubis protection, reject that user agent before serving a challenge.
    options.add_argument(f"--user-agent={_CHROME_USER_AGENT}")
    return options


def _get_local_firefox_driver() -> WebDriver:
    options = FirefoxOptions()
    return webdriver.Firefox(
        service=FirefoxService(executable_path="/usr/bin/geckodriver"),
        options=options,
    )


def _get_local_headless_firefox_driver() -> WebDriver:
    options = FirefoxOptions()
    options.add_argument("--headless")
    return webdriver.Firefox(
        service=FirefoxService(executable_path="/usr/bin/geckodriver"),
        options=options,
    )
