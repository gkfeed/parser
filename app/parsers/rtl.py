import time
from typing import override
from bs4 import BeautifulSoup, Tag

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By

from app.extensions.parsers.selenium import SeleniumParserExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin


class RTLSeriesFeed(PostToItemsMixin, SeleniumParserExtension):
    _selenium_wait_time = 20
    _base_url = "https://plus.rtl.de"

    @property
    @override
    async def _posts(self) -> list[Tag]:
        html = await self.get_html(self.feed.url)
        soup = BeautifulSoup(html, "html.parser")
        return [
            link
            for link in soup.find_all(class_="series-teaser__link")
            if isinstance(link, Tag)
        ]

    @override
    async def _get_post_title(self, post: Tag) -> str:
        return post.h3.text if post.h3 and isinstance(post.h3, Tag) else ""

    @override
    async def _get_post_link(self, post: Tag) -> str:
        if "href" in post.attrs and isinstance(post["href"], str):
            return self._base_url + str(post["href"])
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
