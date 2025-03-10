from datetime import timedelta, datetime

from bs4 import Tag

from app.utils.datetime import convert_datetime, constant_datetime
from app.serializers.feed import Item
from app.extentions.parsers.http import HttpParserExtention
from app.extentions.parsers.cache import CacheFeedExtention


class OneFootballFeed(HttpParserExtention, CacheFeedExtention):
    __base_url = "https://onefootball.com"
    _cache_storage_time = timedelta(hours=1)

    @property
    async def items(self) -> list[Item]:
        return [
            Item(
                title=self._get_match_title(m),
                text=self._get_match_title(m),
                date=self._get_match_datetime(m),
                link=self._get_match_link(m),
            )
            for m in await self._matches
        ]

    @property
    async def _matches(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)
        links = soup.find_all("a")
        return [links[16], links[18]]

    def _get_match_title(self, match: Tag) -> str:
        try:
            first_team_name = match.find_all("span")[0].text
            second_team_name = match.find_all("span")[2].text

            return first_team_name + " vs " + second_team_name
        except IndexError:
            raise ValueError

    def _get_match_datetime(self, match: Tag) -> datetime:
        try:
            datetime_str = match.find_all("time")[0]["datetime"]
            return convert_datetime(datetime_str)
        except (IndexError, KeyError):
            print("onefootball: return constant datetime")  # log
            return constant_datetime

    def _get_match_link(self, match: Tag) -> str:
        try:
            return self.__base_url + match["href"]
        except KeyError:
            raise ValueError
