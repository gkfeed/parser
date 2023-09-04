from datetime import timedelta, datetime

from bs4 import Tag

from app.utils.datetime import convert_datetime
from app.serializers.feed import Item
from ._exceptions import UnavailableFeed
from ._parser import WebParser


class RedditFeed(WebParser):
    __base_url = 'https://libreddit.northboot.xyz/'
    _cache_storage_time = timedelta(hours=1)

    @property
    async def items(self) -> list[Item]:
        try:
            return [
                Item(
                    title=self._get_post_title(p),
                    text=self._get_post_text(p),
                    date=self._get_post_datetime(p),
                    link=self._get_post_link(p),
                )
                for p in await self._posts
            ]
        except (UnavailableFeed, ValueError):
            return []

    @property
    async def _posts(self) -> list[Tag]:
        url = self.__base_url + '/'.join(self.feed.url.split('/')[3:])
        soup = await self.get_soup(url)
        return [p for p in soup.find_all(class_='post')]

    def _get_post_title(self, post: Tag) -> str:
        try:
            return post.find_all(class_='post_title')[0].text
        except IndexError:
            raise ValueError

    def _get_post_text(self, post: Tag) -> str:
        try:
            body = post.find_all(class_='post_body')[0]

            text = ''
            for p in body.find_all('p'):
                text += p.text

            if not text:
                text = self._get_post_title(post)

            return text + '<br/><br/>r/' + self.feed.url.split('/')[-1]
        except IndexError:
            raise ValueError

    def _get_post_datetime(self, post: Tag) -> datetime:
        try:
            datetime_str = post.find_all(class_='created')[0]['title']
            return convert_datetime(datetime_str)
        except IndexError:
            raise ValueError

    def _get_post_link(self, post: Tag) -> str:
        try:
            base_url = 'https://www.reddit.com/'
            post_href = post.find_all(class_='post_comments')[0]['href']
            return base_url + '/'.join(post_href.split('/')[:-2])
        except IndexError:
            raise ValueError
