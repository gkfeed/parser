from datetime import datetime, timedelta

from bs4 import Tag

from app.extensions.parsers.http import HttpParserExtension

from app.serializers.feed import Item
from app.utils.datetime import constant_datetime


class ShikiOngoingFeed(HttpParserExtension):
    _cache_storage_time = timedelta(hours=1)
    _cache_storage_time_if_success = timedelta(days=1)

    @property
    async def items(self) -> list[Item]:
        soup = await self.get_soup(self.feed.url)

        container = soup.find("div", class_="fc-ongoings")
        if not isinstance(container, Tag):
            return []

        articles = container.find_all("article")

        return [
            Item(
                title=self._get_item_title(article),
                text=self._get_item_title(article),
                date=self._get_item_date(article),
                link=self._get_item_link(article),
            )
            for article in articles
            if isinstance(article, Tag)
        ]

    def _get_item_title(self, article: Tag) -> str:
        title_tag = article.find("span", class_="name-en")
        if title_tag and isinstance(title_tag, Tag):
            return title_tag.text
        raise ValueError("Title not found")

    def _get_item_link(self, article: Tag) -> str:
        link_tag = article.find("a")
        if link_tag and isinstance(link_tag, Tag):
            href = link_tag.get("href")
            if isinstance(href, str):
                return href
        raise ValueError("Link not found")

    def _get_item_date(self, article: Tag) -> datetime:
        date_meta = article.find("meta", itemprop="dateCreated")
        if (
            date_meta
            and isinstance(date_meta, Tag)
            and (date_content := date_meta.get("content"))
            and isinstance(date_content, str)
        ):
            return datetime.fromisoformat(date_content)
        return constant_datetime
