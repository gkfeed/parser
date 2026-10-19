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
            if not isinstance(link, Tag) or link.name != "a" or not link.has_attr("href"):
                continue
            href = link["href"]
            if not isinstance(href, str) or not href.startswith(self.feed.url):
                continue
            video_links.append(href)

        return video_links
