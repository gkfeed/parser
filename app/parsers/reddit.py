import json
from datetime import timedelta, datetime
from typing import override

from bs4 import Tag

from app.utils.datetime import convert_datetime, constant_datetime
from app.serializers.feed import Item
from app.services.http import HttpService
from app.services.hash import HashService
from app.services.url_ranker import URLRanker
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemsHashExtension


class RedditFeed(ItemsHashExtension, HttpParserExtension, CacheFeedExtension):
    _cache_storage_time = timedelta(hours=1)
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
    async def items(self) -> list[Item]:
        return [
            Item(
                title=self._get_post_title(p),
                text=self._get_post_text(p),
                date=self._get_post_datetime(p),
                link=self._get_post_link(p),
            )
            for p in await self._posts
        ]

    @property
    async def _posts(self) -> list[Tag]:
        base_urls = await self._get_base_urls()
        posts: list[Tag] = []

        for base_url in base_urls:
            try:
                url = base_url + "/" + "/".join(self.feed.url.split("/")[3:])
                soup = await self.get_soup(url)
                posts = [p for p in soup.find_all(class_="post") if isinstance(p, Tag)]
                if not posts:
                    self.__url_ranker.demote_url(base_url)
                    continue
                self.__url_ranker.promote_url(base_url)
            except Exception:
                self.__url_ranker.demote_url(base_url)
                continue

        return posts

    def _get_post_title(self, post: Tag) -> str:
        title_tag = post.find(class_="post_title")
        if title_tag and isinstance(title_tag, Tag):
            return title_tag.text
        return ""

    def _get_post_text(self, post: Tag) -> str:
        body = post.find(class_="post_body")
        text = ""
        if body and isinstance(body, Tag):
            for p in body.find_all("p"):
                if isinstance(p, Tag):
                    text += p.text

        if not text:
            text = self._get_post_title(post)

        feed_url_parts = self.feed.url.split("/")
        subreddit_name = (
            feed_url_parts[-1] if feed_url_parts and feed_url_parts[-1] else ""
        )
        return text + "<br/><br/>r/" + subreddit_name

    def _get_post_datetime(self, post: Tag) -> datetime:
        datetime_tag = post.find(class_="created")
        if (
            datetime_tag
            and isinstance(datetime_tag, Tag)
            and "title" in datetime_tag.attrs
        ):
            datetime_str = datetime_tag["title"]
            if isinstance(datetime_str, str):
                return convert_datetime(datetime_str)
        return constant_datetime

    def _get_post_link(self, post: Tag) -> str:
        base_url = "https://www.reddit.com/"
        comments_tag = post.find(class_="post_comments")
        if (
            comments_tag
            and isinstance(comments_tag, Tag)
            and "href" in comments_tag.attrs
        ):
            post_href = comments_tag["href"]
            if isinstance(post_href, str):
                return base_url + "/".join(post_href.split("/")[:-2])
        raise ValueError
