import json
from datetime import datetime, timedelta
from typing import ClassVar, override
from urllib.parse import urljoin

import structlog
from bs4 import BeautifulSoup, Tag

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.exceptions import FeedUnavailable
from app.extensions.parsers.hash import ItemLinkHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.services.http import HttpService
from app.services.url_ranker import URLRanker
from app.utils.datetime import parse_datetime
from app.utils.logging import url_log_fields

logger = structlog.get_logger(__name__)


class _InvalidRedditPage(ValueError):
    """A mirror returned neither posts nor a confirmed empty listing."""


class RedditFeed(
    PostToItemsMixin, ItemLinkHashExtension, HttpParserExtension, CacheFeedExtension
):
    _cache_storage_time = timedelta(hours=1)
    _headers: ClassVar[dict[str, str]] = {"User-Agent": "gkfeed-parser/0.1"}
    __instances_url = "https://raw.githubusercontent.com/redlib-org/redlib-instances/main/instances.json"
    __base_urls_cache: list[str] | None = None
    __url_ranker = URLRanker(data_file="data/reddit_url_ranks.json")

    async def _get_base_urls(self) -> list[str]:
        if self.__base_urls_cache:
            return self.__base_urls_cache

        response = await HttpService.get(self.__instances_url)
        instances_data = json.loads(response)
        all_urls = [
            instance["url"]
            for instance in instances_data["instances"]
            if "url" in instance
        ]
        self.__base_urls_cache = self.__url_ranker.get_ranked_urls(all_urls)
        return self.__base_urls_cache

    @property
    @override
    async def _posts(self) -> list[Tag]:
        base_urls = await self._get_base_urls()
        last_error: FeedUnavailable | _InvalidRedditPage | None = None

        for base_url in base_urls:
            try:
                posts = await self._get_instance_posts(base_url)
            except (FeedUnavailable, _InvalidRedditPage) as error:
                last_error = error
                self.__url_ranker.demote_url(base_url)
                logger.warning(
                    "reddit_mirror_failed",
                    **url_log_fields(base_url, field="mirror"),
                    reason=(
                        error.reason
                        if isinstance(error, FeedUnavailable)
                        else "invalid_page"
                    ),
                )
                continue

            self.__url_ranker.promote_url(base_url)
            return posts

        reason = "no_mirrors_available" if last_error is None else "invalid_page"
        retry_at = None
        if isinstance(last_error, FeedUnavailable):
            reason = last_error.reason
            retry_at = last_error.retry_at
        raise FeedUnavailable(
            self.feed.url, f"reddit_mirrors_exhausted:{reason}", retry_at
        ) from last_error

    async def _get_instance_posts(self, base_url: str) -> list[Tag]:
        url = base_url + "/" + "/".join(self.feed.url.split("/")[3:])
        return self._extract_posts(await self.get_soup(url))

    @override
    def _validate_html(self, url: str, html: bytes) -> None:
        self._extract_posts(BeautifulSoup(html, "html.parser"))

    def _extract_posts(self, soup: BeautifulSoup) -> list[Tag]:
        if soup.select_one("#challenge-form, #cf-challenge-running, .cf-turnstile"):
            raise FeedUnavailable(self.feed.url, "reddit_mirror_challenge")
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
            raise _InvalidRedditPage(
                "Reddit mirror returned neither posts nor a confirmed empty listing"
            )
        return []

    @override
    async def _get_post_title(self, post: Tag) -> str:
        title_tag = post.find(class_="post_title")
        if isinstance(title_tag, Tag):
            return title_tag.text
        return ""

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
        comments_tag = post.find(class_="post_comments")
        if isinstance(comments_tag, Tag):
            post_href = comments_tag.get("href")
            if isinstance(post_href, str):
                return urljoin("https://www.reddit.com", post_href)
        raise ValueError
