from datetime import datetime, timedelta, timezone

from app.serializers.feed import Item
from app.extentions.parsers.http import HttpParserExtention
from app.extentions.parsers.cache import CacheFeedExtention


class LiveballFeed(HttpParserExtention, CacheFeedExtention):
    _cache_storage_time = timedelta(hours=1)

    @property
    async def items(self) -> list[Item]:
        items = []
        soup = await self.get_soup(self.feed.url)

        top_match_container = soup.find("section", class_="top_match_section")
        if not top_match_container:
            return []

        matches = top_match_container.select("div.top_match div.league_block")
        for match in matches:
            if not match or not hasattr(match, "select_one"):
                continue

            league_elem = match.select_one(".tm_league_name")
            if not league_elem:
                continue
            league_name = league_elem.get_text(strip=True)

            team1_elem = match.select_one(".t_left .league_title")
            team2_elem = match.select_one(".t_right .league_title")
            if not team1_elem or not team2_elem:
                continue
            team1 = team1_elem.get_text(strip=True)
            team2 = team2_elem.get_text(strip=True)

            timer_elem = match.select_one(".tm_timer")
            if not timer_elem:
                continue
            try:
                timestamp_str = timer_elem.get("value")
                timestamp = int(str(timestamp_str))
            except ValueError:
                continue

            match_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)

            link_elem = match.select_one("a.la")
            if not link_elem:
                continue
            match_url = link_elem.get("href")
            if not match_url:
                continue

            match_url = str(match_url)
            if not match_url.startswith("http"):
                match_url = self.feed.url.rstrip("/") + match_url

            items.append(
                Item(
                    title=f"{team1} vs {team2} - {league_name}",
                    text=f"{team1} vs {team2} - {league_name}",
                    date=match_time,
                    link=match_url,
                )
            )

        return items
