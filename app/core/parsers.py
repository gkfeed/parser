from typing import Type

from app.serializers.feed import Feed, Item
from app.extentions.parsers.base import BaseFeed


class FeedParsingContext:
    def __init__(self) -> None:
        self._parsers: dict[str, Type[BaseFeed]] = {}

    def register_parser(self, feed_type: str, parser: Type[BaseFeed]):
        self._parsers[feed_type] = parser

    def get_parser_initial_data(self, feed: Feed) -> dict:
        parser = self._parsers[feed.type]
        return parser(feed, {}).data

    async def execute_parser(self, feed: Feed, data: dict) -> list[Item]:
        parser = self._parsers[feed.type]
        return await parser(feed, data).items
