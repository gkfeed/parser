from datetime import timedelta, datetime
from typing import override

from bs4 import Tag

from app.utils.datetime import convert_datetime
from app.serializers.feed import Item
from app.services.hash import HashService
from app.extentions.parsers.http import HttpParserExtention
from app.extentions.parsers.cache import CacheFeedExtention
from app.extentions.parsers.hash import ItemsHashExtension


class RedditFeed(ItemsHashExtension, HttpParserExtention, CacheFeedExtention):
    __base_url = "https://libreddit.northboot.xyz/"
    _cache_storage_time = timedelta(hours=1)

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
        url = self.__base_url + "/".join(self.feed.url.split("/")[3:])
        soup = await self.get_soup(url)
        return [p for p in soup.find_all(class_="post")]

    def _get_post_title(self, post: Tag) -> str:
        try:
            return post.find_all(class_="post_title")[0].text
        except IndexError:
            raise ValueError

    def _get_post_text(self, post: Tag) -> str:
        try:
            body = post.find_all(class_="post_body")[0]

            text = ""
            for p in body.find_all("p"):
                text += p.text

            if not text:
                text = self._get_post_title(post)

            return text + "<br/><br/>r/" + self.feed.url.split("/")[-1]
        except IndexError:
            raise ValueError

    def _get_post_datetime(self, post: Tag) -> datetime:
        try:
            datetime_str = post.find_all(class_="created")[0]["title"]
            return convert_datetime(datetime_str)
        except IndexError:
            raise ValueError

    def _get_post_link(self, post: Tag) -> str:
        try:
            base_url = "https://www.reddit.com/"
            post_href = post.find_all(class_="post_comments")[0]["href"]
            return base_url + "/".join(post_href.split("/")[:-2])
        except IndexError:
            raise ValueError
