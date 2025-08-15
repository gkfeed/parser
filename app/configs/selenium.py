from selenium import webdriver
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService

from app.utils.is_in_docker import IS_IN_DOCKER

SELENIUM_COOKIES_PATH = "/data/cookies.pkl"
IS_HEADLESS = False


def get_driver() -> WebDriver:
    if IS_IN_DOCKER:
        return _get_docker_driver()
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
        "http://10.5.0.5:4444",
        options=webdriver.ChromeOptions(),
    )


def _get_local_headless_chrome_driver() -> WebDriver:
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    return webdriver.Chrome(
        service=Service(executable_path="/usr/bin/chromedriver"),
        options=options,
    )


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
