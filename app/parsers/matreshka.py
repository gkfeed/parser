from datetime import timedelta
from urllib.parse import urljoin
from typing import override

from bs4 import Tag

from app.extensions.parsers.selenium import SeleniumParserExtension
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin


class MatreshkaFeed(PostToItemsMixin, SeleniumParserExtension, CacheFeedExtension):
    _cache_storage_time = timedelta(days=1)
    _selenium_wait_time = 20

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)
        return [
            card
            for card in soup.select(".video-card-container")
            if isinstance(card, Tag)
            and card.select_one(".video-card__title[href]")
        ]

    @override
    async def _get_post_title(self, post: Tag) -> str:
        soup = await self.get_soup(self.feed.url)
        channel_title = self._extract_channel_title(soup)
        link_element = post.select_one(".video-card__title[href]")
        if not link_element:
            raise ValueError("Could not find video title link")
        title = link_element.text.strip()
        return f"{channel_title} - {title}"

    @override
    async def _get_post_link(self, post: Tag) -> str:
        link_element = post.select_one(".video-card__title[href]")
        if not link_element:
            raise ValueError("Could not find video link")
        relative_url = link_element["href"]
        return urljoin(self.feed.url, str(relative_url))

    def _extract_channel_title(self, soup: Tag) -> str:
        title_tag = soup.select_one("title")
        if title_tag and title_tag.text:
            return title_tag.text.split("|")[0].strip()
        return "Unknown Channel"
