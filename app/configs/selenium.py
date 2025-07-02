from selenium import webdriver
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.chrome.service import Service

from app.utils.is_in_docker import IS_IN_DOCKER


def get_driver() -> WebDriver:
    if IS_IN_DOCKER:
        return get_docker_driver()
    return get_local_chrome_driver()


def get_local_chrome_driver() -> WebDriver:
    return webdriver.Chrome(
        service=Service(executable_path="/usr/bin/chromedriver"),
        options=webdriver.ChromeOptions(),
    )


def get_docker_driver() -> WebDriver:
    return webdriver.Remote(
        "http://10.5.0.5:4444",
        options=webdriver.ChromeOptions(),
    )


def get_local_headless_chrome_driver() -> WebDriver:
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    return webdriver.Chrome(
        service=Service(executable_path="/usr/bin/chromedriver"),
        options=options,
    )
