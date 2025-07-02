from bs4 import Tag

from app.extensions.parsers.selenium import SeleniumParserExtension
from ._base import BaseTikTokFeed


class TikTokSeleniumFeed(BaseTikTokFeed, SeleniumParserExtension):
    _selenium_wait_time = 20
    _should_load_cookies = True
    _should_save_cookies = True

    @property
    async def _video_links(self) -> list[str]:
        soup = await self.get_soup(self.feed.url)

        links = soup.find_all("a")

        video_links = []
        for link in links:
            if isinstance(link, Tag) and link.name == "a" and link.has_attr("href"):
                href = link["href"]
                if isinstance(href, str) and href.startswith(self.feed.url):
                    video_links.append(href)

        return video_links
