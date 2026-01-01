from typing import Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from selenium.webdriver.remote.webdriver import WebDriver

from app.services.container import Container
from .selenium import get_driver
from .db import session_factory


@dataclass
class Data:
    selenium_web_driver: Callable[[], WebDriver]
    db_session: async_sessionmaker[AsyncSession]


Container.setup(Data(selenium_web_driver=get_driver, db_session=session_factory))
