import json
from datetime import datetime
from typing import override
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag

from app.extensions.parsers.http import HttpParserExtension
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin


class LiquidpediaFeed(
    PostToItemsMixin, ItemsHashExtension, HttpParserExtension, CacheFeedExtension
):
    _headers = {
        **HttpParserExtension._headers,
        "User-Agent": "gkfeed-parser/0.1 (https://github.com/gkfeed/parser)",
    }

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self._get_page_soup()
        upcoming_matches_heading = soup.find(id="Upcoming_Matches")
        if isinstance(upcoming_matches_heading, Tag):
            heading_container = upcoming_matches_heading.parent
            if not isinstance(heading_container, Tag):
                raise ValueError("Upcoming matches heading container not found")

            matches_container = heading_container.find_next_sibling()
            if not isinstance(matches_container, Tag):
                raise ValueError("Upcoming matches container not found")

            matches = matches_container.select(".match-info")
        else:
            # Team pages without scheduled matches omit the Upcoming Matches
            # heading. Their recent matches are rendered using the new table2
            # markup instead.
            matches = soup.select(".match-table-wrapper tr.table2__row--body")

        return [match for match in matches if isinstance(match, Tag)]

    @override
    async def _get_post_title(self, post: Tag) -> str:
        team_names: list[str] = []
        for opponent in post.select(".match-info-opponent-row"):
            name_tag = opponent.select_one(".name")
            if not isinstance(name_tag, Tag):
                raise ValueError("Team name not found")
            team_names.append(name_tag.get_text(" ", strip=True))

        if not team_names:
            team_names = [
                name_tag.get_text(" ", strip=True)
                for name_tag in post.select(".block-team .name")
                if isinstance(name_tag, Tag)
            ]
            if len(team_names) == 1:
                team_names.insert(0, self._get_team_name_from_url())

        if len(team_names) != 2 or not all(team_names):
            raise ValueError("Expected two team names")

        return f"{team_names[0]} vs {team_names[1]}"

    @override
    async def _get_post_link(self, post: Tag) -> str:
        for link_tag in post.select("a[href]"):
            href = link_tag.get("href")
            if not isinstance(href, str):
                continue

            link = urljoin(self.feed.url, href)
            url = urlsplit(link)
            page = unquote(url.path.rstrip("/").rsplit("/", 1)[-1])
            if page.startswith("Match:"):
                return link

            title = parse_qs(url.query).get("title", [""])[0]
            if title.startswith("Match:"):
                return link

        raise ValueError("Match page link not found")

    @override
    async def _get_post_datetime(self, post: Tag) -> datetime:
        timer_span = post.select_one(".timer-object[data-timestamp]")
        if not isinstance(timer_span, Tag):
            raise ValueError("Timer span not found")

        timestamp_str = timer_span.get("data-timestamp")
        if not isinstance(timestamp_str, str):
            raise ValueError("data-timestamp not found")

        return datetime.fromtimestamp(int(timestamp_str))

    async def _get_page_soup(self) -> BeautifulSoup:
        response = json.loads(await self.get_html(self._get_api_url()))
        try:
            html = response["parse"]["text"]["*"]
        except (KeyError, TypeError) as error:
            raise ValueError("Unexpected Liquipedia API response") from error

        if not isinstance(html, str):
            raise ValueError("Liquipedia API response does not contain HTML")

        return BeautifulSoup(html, "html.parser")

    def _get_api_url(self) -> str:
        url = urlsplit(self.feed.url)
        path_parts = url.path.strip("/").split("/", maxsplit=1)
        if len(path_parts) != 2 or not all(path_parts):
            raise ValueError("Invalid Liquipedia page URL")

        wiki, page = path_parts
        query = urlencode(
            {
                "action": "parse",
                "page": unquote(page),
                "prop": "text",
                "format": "json",
            }
        )
        return urlunsplit((url.scheme, url.netloc, f"/{wiki}/api.php", query, ""))

    def _get_team_name_from_url(self) -> str:
        page = unquote(urlsplit(self.feed.url).path.rstrip("/").rsplit("/", 1)[-1])
        team_name = page.replace("_", " ").strip()
        if not team_name:
            raise ValueError("Could not extract team name from Liquipedia URL")
        return team_name
