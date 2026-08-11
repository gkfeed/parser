import json
from datetime import datetime, timedelta
from typing import ClassVar, override
from urllib.parse import urljoin

from bs4 import Tag

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.serializers.feed import Item
from app.services.hash import HashService
from app.services.http import HttpService
from app.services.url_ranker import URLRanker
from app.utils.datetime import convert_datetime


class RedditFeed(
    PostToItemsMixin, ItemsHashExtension, HttpParserExtension, CacheFeedExtension
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

    @override
    async def _generate_hash(self, item: Item) -> str:
        return HashService.hash_str(item.link)

    @property
    @override
    async def _posts(self) -> list[Tag]:
        base_urls = await self._get_base_urls()

        for base_url in base_urls:
            try:
                url = base_url + "/" + "/".join(self.feed.url.split("/")[3:])
                soup = await self.get_soup(url)
                posts = [
                    post
                    for post in soup.find_all(class_="post")
                    if isinstance(post, Tag)
                ]
                if not posts:
                    self.__url_ranker.demote_url(base_url)
                    continue
                self.__url_ranker.promote_url(base_url)
                return posts
            except Exception:  # noqa: BLE001 - try the next public instance on any failure
                self.__url_ranker.demote_url(base_url)
                continue

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
            if isinstance(datetime_str, str):
                return convert_datetime(datetime_str)
        return await super()._get_post_datetime(post)

    @override
    async def _get_post_link(self, post: Tag) -> str:
        comments_tag = post.find(class_="post_comments")
        if isinstance(comments_tag, Tag):
            post_href = comments_tag.get("href")
            if isinstance(post_href, str):
                return urljoin("https://www.reddit.com", post_href)
        raise ValueError
