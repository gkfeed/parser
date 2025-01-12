import time
from typing import override
from bs4 import BeautifulSoup

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By

from app.utils.datetime import constant_datetime
from app.extentions.parsers.selenium import SeleniumParserExtention
from app.serializers.feed import Item


class RTLSerieFeed(SeleniumParserExtention):
    _selenium_wait_time = 20
    _base_url = "https://plus.rtl.de"

    @property
    async def items(self) -> list[Item]:
        html = await self.get_html(self.feed.url)
        soup = BeautifulSoup(html, "html.parser")
        links = soup.find_all(class_="series-teaser__link")
        items = [
            Item(
                title=l.h3.text,
                text=l.h3.text,
                date=constant_datetime,
                link=self._base_url + l["href"],
            )
            for l in links
        ]
        return items

    @override
    def make_actions(self, driver: WebDriver):
        # Button Kostenlose Folden in top of the page
        button = driver.find_element(
            By.XPATH,
            "/html/body/plus-root/ng-component/main/div/watch-watch/watch-format/section/watch-format-tab-navigation/mat-tab-group/mat-tab-header/div/div/div/div[2]/div",
        )
        driver.execute_script("arguments[0].click();", button)
        time.sleep(self._selenium_wait_time)
