import re
from datetime import datetime, timedelta
from typing import override
from urllib.parse import urljoin

from bs4 import Tag

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin
from app.utils.datetime import constant_datetime, convert_datetime


class OneFootballFeed(PostToItemsMixin, HttpParserExtension, CacheFeedExtension):
    __base_url = "https://onefootball.com"
    __match_path = re.compile(r"^/[^/]+/match/\d+/?$")
    _cache_storage_time = timedelta(hours=1)

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)
        return [
            link
            for link in soup.find_all("a", href=self.__match_path, limit=2)
            if isinstance(link, Tag)
        ]

    @override
    async def _get_post_title(self, post: Tag) -> str:
        team_names = post.select('span[class*="simpleMatchCardTeam__name"]')
        if len(team_names) != 2:
            raise ValueError("Could not find both team names")

        return " vs ".join(team.get_text(strip=True) for team in team_names)

    @override
    async def _get_post_datetime(self, post: Tag) -> datetime:
        time_tag = post.find("time")
        datetime_attr = time_tag.get("datetime") if isinstance(time_tag, Tag) else None
        if isinstance(datetime_attr, str):
            return convert_datetime(datetime_attr)
        return constant_datetime

    @override
    async def _get_post_link(self, post: Tag) -> str:
        if "href" not in post.attrs:
            raise ValueError("Match tag has no 'href' attribute")
        href = post["href"]
        if not isinstance(href, str):
            raise ValueError(  # noqa: TRY004 - malformed page data is a value error
                "Match 'href' attribute is not a string"
            )
        return urljoin(self.__base_url, href)
