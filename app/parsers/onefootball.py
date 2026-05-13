from datetime import timedelta, datetime
from typing import override

from bs4 import Tag

from app.utils.datetime import convert_datetime, constant_datetime
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin


class OneFootballFeed(PostToItemsMixin, HttpParserExtension, CacheFeedExtension):
    __base_url = "https://onefootball.com"
    _cache_storage_time = timedelta(hours=1)

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)
        links = [link for link in soup.find_all("a") if isinstance(link, Tag)]
        # Assuming links[16] and links[18] are always valid and Tag objects after filtering
        if len(links) <= 18:
            return []
        return [links[16], links[18]]

    @override
    async def _get_post_title(self, post: Tag) -> str:
        first_team_span = post.find("span")
        second_team_span = post.find_all("span")

        if not (first_team_span and isinstance(first_team_span, Tag)):
            raise ValueError("Could not find first team span")
        if not (len(second_team_span) > 2 and isinstance(second_team_span[2], Tag)):
            raise ValueError("Could not find second team span")

        first_team_name = first_team_span.text
        second_team_name = second_team_span[2].text

        return first_team_name + " vs " + second_team_name

    @override
    async def _get_post_datetime(self, post: Tag) -> datetime:
        time_tag = post.find("time")
        if time_tag and isinstance(time_tag, Tag) and "datetime" in time_tag.attrs:
            datetime_attr = time_tag["datetime"]
            if isinstance(datetime_attr, str):
                return convert_datetime(datetime_attr)
        return constant_datetime

    @override
    async def _get_post_link(self, post: Tag) -> str:
        if "href" not in post.attrs:
            raise ValueError("Match tag has no 'href' attribute")
        href = post["href"]
        if not isinstance(href, str):
            raise ValueError("Match 'href' attribute is not a string")
        return self.__base_url + href
