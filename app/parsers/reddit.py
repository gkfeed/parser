from datetime import datetime, timedelta
from functools import cached_property
from typing import ClassVar, override
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.exceptions import FeedUnavailable
from app.extensions.parsers.hash import ItemLinkHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.services.redlib import InvalidRedlibPage, RedlibClient
from app.utils.datetime import parse_datetime
from app.utils.html import require_tag, required_attr, required_text


class RedditFeed(
    PostToItemsMixin, ItemLinkHashExtension, HttpParserExtension, CacheFeedExtension
):
    empty_result_delay = timedelta(hours=1)
    _headers: ClassVar[dict[str, str]] = {"User-Agent": "gkfeed-parser/0.1"}

    @cached_property
    def _redlib_client(self) -> RedlibClient:
        return RedlibClient(self.get_html)

    @property
    @override
    async def _posts(self) -> list[Tag]:
        html = await self._redlib_client.get_page_html(self.feed.url)
        return self._extract_posts(BeautifulSoup(html, "html.parser"))

    @override
    def _validate_html(self, url: str, html: bytes) -> None:
        self._extract_posts(BeautifulSoup(html, "html.parser"))

    def _extract_posts(self, soup: BeautifulSoup) -> list[Tag]:
        title = soup.title.get_text(strip=True).lower() if soup.title else ""
        if soup.select_one(
            "#challenge-form, #cf-challenge-running, .cf-turnstile, #anubis_challenge"
        ) or title in {
            "just a moment...",
            "checking you are not a bot",
            "making sure you're not a bot!",
        }:
            raise FeedUnavailable(self.feed.url, "reddit_mirror_challenge")
        if soup.select_one("form input[type='password']"):
            raise FeedUnavailable(self.feed.url, "reddit_mirror_login")
        if title in {"access denied", "forbidden", "blocked", "403 forbidden"}:
            raise FeedUnavailable(self.feed.url, "reddit_mirror_blocked")
        if soup.select_one("#error"):
            raise FeedUnavailable(self.feed.url, "reddit_mirror_error_page")
        posts = [post for post in soup.find_all(class_="post") if isinstance(post, Tag)]
        if posts:
            return posts

        # Redlib renders this message alongside #posts for no_posts.
        empty_message = soup.select_one("#column_one > center")
        if (
            soup.select_one("#posts") is None
            or empty_message is None
            or empty_message.get_text(strip=True) != "No posts were found."
        ):
            raise InvalidRedlibPage(
                "Reddit mirror returned neither posts nor a confirmed empty listing"
            )
        return []

    @override
    async def _get_post_title(self, post: Tag) -> str:
        title_tag = require_tag(post.find(class_="post_title"), "Reddit post title")
        return required_text(title_tag, "Reddit post title", separator=" ")

    @override
    async def _get_post_text(self, post: Tag) -> str:
        body = post.find(class_="post_body")
        text = (
            "".join(
                paragraph.text
                for paragraph in body.find_all("p")
                if isinstance(paragraph, Tag)
            )
            if isinstance(body, Tag)
            else ""
        )

        if not text:
            text = await self._get_post_title(post)

        subreddit_name = self.feed.url.rpartition("/")[2]
        return text + "<br/><br/>r/" + subreddit_name

    @override
    async def _get_post_datetime(self, post: Tag) -> datetime:
        datetime_tag = post.find(class_="created")
        if isinstance(datetime_tag, Tag):
            datetime_str = datetime_tag.get("title")
            if isinstance(datetime_str, str) and datetime_str.strip():
                return parse_datetime(datetime_str)
        return await super()._get_post_datetime(post)

    @override
    async def _get_post_link(self, post: Tag) -> str:
        comments_tag = require_tag(
            post.find(class_="post_comments"), "Reddit comments link"
        )
        post_href = required_attr(comments_tag, "href", "Reddit comments link")
        return urljoin("https://www.reddit.com", post_href)
