from collections.abc import Callable
from dataclasses import dataclass

from selenium.webdriver.remote.webdriver import WebDriver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.container import Container

from .db import session_factory
from .selenium import get_driver


@dataclass
class Data:
    selenium_web_driver: Callable[[], WebDriver]
    db_session: async_sessionmaker[AsyncSession]


Container.setup(Data(selenium_web_driver=get_driver, db_session=session_factory))
