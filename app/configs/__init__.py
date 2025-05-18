from typing import Callable
from dataclasses import dataclass

from selenium.webdriver.remote.webdriver import WebDriver

from app.services.container import Container
from .selenium import get_driver


@dataclass
class Data:
    selenium_web_driver: Callable[[], WebDriver]


Container.setup(Data(selenium_web_driver=get_driver))
