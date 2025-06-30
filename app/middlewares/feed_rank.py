from typing import Any, Callable, Awaitable

from app.middlewares._base import BaseMiddleware
from app.models.feed import Feed
from app.models.item import Item
from app.services.url_ranker import URLRanker


class FeedRankMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self.__url_ranker = URLRanker(data_file="data/feed_url_ranks.json")
        self.__rank_threshold = 5  # Skip parsing if rank is above this threshold

    async def __call__(
        self,
        parser: Callable[[Feed, dict[str, Any]], Awaitable[list[Item]]],
        feed: Feed,
        data: dict,
    ) -> list[Item]:
        feed_url = str(feed.url)
        current_rank = self.__url_ranker.ranks.get(feed_url, 0)

        if current_rank >= self.__rank_threshold:
            print(f"Skipping parsing for {feed_url} due to high rank ({current_rank})")
            return []

        items = await parser(feed, data)

        if not items:
            self.__url_ranker.demote_url(feed_url)
            print(
                f"Demoted {feed_url}. New rank: {self.__url_ranker.ranks.get(feed_url)}"
            )
        else:
            self.__url_ranker.promote_url(feed_url)
            print(
                f"Promoted {feed_url}. New rank: {self.__url_ranker.ranks.get(feed_url)}"
            )

        return items
