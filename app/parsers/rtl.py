import time
from typing import override
from bs4 import BeautifulSoup, Tag

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By

from app.utils.datetime import constant_datetime
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.serializers.feed import Item


class RTLSeriesFeed(SeleniumParserExtension):
    _selenium_wait_time = 20
    _base_url = "https://plus.rtl.de"

    @property
    async def items(self) -> list[Item]:
        html = await self.get_html(self.feed.url)
        soup = BeautifulSoup(html, "html.parser")
        links = soup.find_all(class_="series-teaser__link")
        items = [
            Item(
                title=self._extract_item_title(link),
                text=self._extract_item_text(link),
                date=constant_datetime,
                link=self._get_item_link(link),
            )
            for link in links
            if isinstance(link, Tag)
        ]
        return items

    def _extract_item_title(self, link: Tag) -> str:
        return link.h3.text if link.h3 and isinstance(link.h3, Tag) else ""

    def _extract_item_text(self, link: Tag) -> str:
        return link.h3.text if link.h3 and isinstance(link.h3, Tag) else ""

    def _get_item_link(self, link_elem: Tag) -> str:
        if "href" in link_elem.attrs and isinstance(link_elem["href"], str):
            return self._base_url + str(link_elem["href"])
        raise ValueError("Link element does not contain a valid href")

    @override
    def make_actions(self, driver: WebDriver):
        # Button Kostenlose Folden in top of the page
        button = driver.find_element(
            By.XPATH,
            "/html/body/plus-root/ng-component/main/div/watch-watch/watch-format/watch-format-tab-navigation/mat-tab-group/mat-tab-header/div/div/div/div[2]/div",
        )
        driver.execute_script("arguments[0].click();", button)
        time.sleep(self._selenium_wait_time)
