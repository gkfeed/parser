from datetime import UTC, datetime, timedelta
from typing import override

from bs4 import BeautifulSoup, Tag

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemIdentityHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.utils.html import require_tag, required_attr, required_text


class RanobeMeFeed(
    PostToItemsMixin, ItemIdentityHashExtension, HttpParserExtension, CacheFeedExtension
):
    _base_url = "https://ranobe.me"
    _cache_storage_time = timedelta(hours=1)

    @override
    def _validate_html(self, url: str, html: bytes) -> None:
        soup = BeautifulSoup(html, "html.parser")
        if url == self._base_url + "/news":
            self._validate_news(soup)
            return
        self._get_chapter_text(soup)

    def _validate_news(self, soup: BeautifulSoup) -> None:
        cards = soup.select(".news_item")
        if not cards:
            raise ValueError("RanobeMe news cards are missing")
        # Validate every card before filtering by book, including cached pages.
        for card in cards:
            title_link = require_tag(
                card.select_one(".FicTable_Title a"), "RanobeMe news book"
            )
            href = required_attr(title_link, "href", "RanobeMe news book")
            if not href.strip():
                raise ValueError("RanobeMe news book has no usable link")
            required_text(title_link, "RanobeMe news book")
            self._get_chapter_links(title_link)

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self._base_url + "/news")
        feed_path = self.feed.url.removeprefix(self._base_url).rstrip("/")
        chapters: dict[str, Tag] = {}

        for title_link in soup.select(f'.FicTable_Title a[href="{feed_path}"]'):
            chapters.update(self._get_chapter_links(title_link))

        return list(chapters.values())

    def _get_chapter_links(self, title_link: Tag) -> dict[str, Tag]:
        card = title_link.find_parent(class_="news_item")
        if not isinstance(card, Tag):
            raise ValueError(  # noqa: TRY004 - missing page data is a value error
                f"RanobeMe news card is missing for {self.feed.url}"
            )
        chapter_list = card.select_one("div.news_chapters_list")
        if chapter_list is None:
            raise ValueError(f"RanobeMe chapter list is missing for {self.feed.url}")
        chapter_links = chapter_list.select("a")
        if not chapter_links:
            raise ValueError(f"RanobeMe news card has no chapters for {self.feed.url}")
        chapters: dict[str, Tag] = {}
        for chapter_link in chapter_links:
            href = chapter_link.get("href")
            if not isinstance(href, str) or not href.strip():
                raise ValueError(
                    f"RanobeMe chapter has no usable link for {self.feed.url}"
                )
            chapters[href] = chapter_link
        return chapters

    @override
    async def _get_post_title(self, post: Tag) -> str:
        if title := post.get_text(strip=True):
            return title
        raise ValueError("Could not find post title.")

    @override
    async def _get_post_text(self, post: Tag) -> str:
        soup = await self.get_soup(await self._get_post_link(post))
        return self._get_chapter_text(soup)

    def _get_chapter_text(self, soup: BeautifulSoup) -> str:
        chapter = require_tag(soup.find(class_="chapter"), "RanobeMe chapter")
        paragraphs = chapter.select("p")
        if not any(p.get_text(strip=True) for p in paragraphs):
            raise ValueError("RanobeMe chapter has no paragraph text")
        return "<br/><br/>".join(p.text for p in paragraphs)

    @override
    async def _get_post_link(self, post: Tag) -> str:
        href = post.get("href")
        if isinstance(href, str):
            return self._base_url + href
        raise ValueError("Could not find post link.")

    @override
    async def _get_post_datetime(self, post: Tag) -> datetime:
        chapter_list = post.find_parent("div", class_="news_chapters_list")
        news_date = (
            chapter_list.find_next_sibling("div", class_="news_date")
            if isinstance(chapter_list, Tag)
            else None
        )
        uptodate_tag = (
            news_date.find(class_="uptodate") if isinstance(news_date, Tag) else None
        )
        if isinstance(uptodate_tag, Tag):
            timestamp_str = uptodate_tag.get("data-time")
            if isinstance(timestamp_str, str):
                timestamp = int(timestamp_str)
                return datetime.fromtimestamp(timestamp, UTC)
        raise ValueError("Could not determine update time.")
