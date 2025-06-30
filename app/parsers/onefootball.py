from datetime import timedelta, datetime

from bs4 import Tag

from app.utils.datetime import convert_datetime, constant_datetime
from app.serializers.feed import Item
from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.cache import CacheFeedExtension


class OneFootballFeed(HttpParserExtension, CacheFeedExtension):
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
        links = [link for link in soup.find_all("a") if isinstance(link, Tag)]
        # Assuming links[16] and links[18] are always valid and Tag objects after filtering
        return [links[16], links[18]]

    def _get_match_title(self, match: Tag) -> str:
        first_team_span = match.find("span")
        second_team_span = match.find_all("span")

        if not (first_team_span and isinstance(first_team_span, Tag)):
            raise ValueError("Could not find first team span")
        if not (len(second_team_span) > 2 and isinstance(second_team_span[2], Tag)):
            raise ValueError("Could not find second team span")

        first_team_name = first_team_span.text
        second_team_name = second_team_span[2].text

        return first_team_name + " vs " + second_team_name

    def _get_match_datetime(self, match: Tag) -> datetime:
        time_tag = match.find("time")
        if time_tag and isinstance(time_tag, Tag) and "datetime" in time_tag.attrs:
            datetime_attr = time_tag["datetime"]
            if isinstance(datetime_attr, str):
                return convert_datetime(datetime_attr)
        return constant_datetime

    def _get_match_link(self, match: Tag) -> str:
        if "href" not in match.attrs:
            raise ValueError("Match tag has no 'href' attribute")
        href = match["href"]
        if not isinstance(href, str):
            raise ValueError("Match 'href' attribute is not a string")
        return self.__base_url + href
