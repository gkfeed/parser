from datetime import timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.utils.datetime import constant_datetime
from app.serializers.feed import Item
from app.extentions.parsers.selenium import SeleniumParserExtention
from app.extentions.parsers.cache import CacheFeedExtention


class MatreshkaFeed(SeleniumParserExtention, CacheFeedExtention):
    _cache_storage_time = timedelta(days=1)
    _selenium_wait_time = 20

    @property
    async def items(self) -> list[Item]:
        soup = await self.get_soup(self.feed.url)
        items = []

        channel_title = self._extract_channel_title(soup)

        video_cards = soup.select(".video-card-container")
        for card in video_cards:
            link_element = card.select_one(".video-card__title[href]")
            if not link_element:
                continue

            relative_url = link_element["href"]
            video_url = urljoin(self.feed.url, str(relative_url))

            title = link_element.text.strip()

            items.append(
                Item(
                    title=f"{channel_title} - {title}",
                    text=f"{channel_title} - {title}",
                    date=constant_datetime,
                    link=video_url,
                )
            )

        return items

    def _extract_channel_title(self, soup: BeautifulSoup) -> str:
        title_tag = soup.select_one("title")
        if title_tag and title_tag.text:
            return title_tag.text.split("|")[0].strip()
        return "Unknown Channel"
