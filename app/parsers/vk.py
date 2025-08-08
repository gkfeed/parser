from datetime import timedelta, datetime, date
from typing import override

from bs4 import Tag

from app.utils.datetime import convert_datetime, constant_datetime
from app.services.hash import HashService
from app.serializers.feed import Item
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemsHashExtension


class VkFeed(ItemsHashExtension, HttpParserExtension, CacheFeedExtension):
    _cache_storage_time = timedelta(hours=1)

    @property
    async def items(self) -> list[Item]:
        return [
            Item(
                title=self._get_post_title(p),
                text=self._get_post_text(p),
                date=constant_datetime,
                link=self._get_post_link(p),
            )
            for p in await self._posts
        ]

    @override
    async def _generate_hash(self, item: Item) -> str:
        return HashService.hash_str(item.link)

    @property
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)
        return [p for p in soup.find_all(class_="post") if isinstance(p, Tag)]

    def _get_post_title(self, post: Tag) -> str:
        try:
            return post.find_all(class_="PostHeaderTitle__authorName")[0].text
        except IndexError:
            raise ValueError

    def _get_post_text(self, post: Tag) -> str:
        try:
            if item := post.find(class_="wall_post_text"):
                return item.text

            if item := post.find(class_="post_video_title"):
                return item.text

            return post.find_all(class_="PostHeaderTitle__authorName")[0].text
        except IndexError:
            raise ValueError

    def _get_post_datetime(self, post: Tag) -> datetime:
        # NOTE: broken
        try:
            datetime_str = post.find_all("time")[0].text
            return self._parse_datetime(datetime_str)
        except IndexError:
            raise ValueError

    def _parse_datetime(self, datetime_str: str) -> datetime:
        if datetime_str.startswith("today"):
            today_str = date.today().strftime("%m/%d/%Y")
            datetime_str = today_str + datetime_str.split("at")[1]

        if datetime_str.startswith("yesterday"):
            yesterday = date.today() - timedelta(days=1)
            yesterday_str = yesterday.strftime("%m/%d/%Y")
            datetime_str = yesterday_str + datetime_str.split("at")[1]

        try:
            return convert_datetime(datetime_str)
        except Exception as e:
            print(e)
            return constant_datetime

    def _get_post_link(self, post: Tag) -> str:
        try:
            link = "https://vk.com/wall" + str(post["id"])[4:]
            return link
        except IndexError:
            raise ValueError
