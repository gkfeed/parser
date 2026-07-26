
from app.extensions.parsers.base import BaseFeed
from app.serializers.feed import Feed, Item


class FeedParsingContext:
    def __init__(self) -> None:
        self._parsers: dict[str, type[BaseFeed]] = {}

    def register_parser(self, feed_type: str, parser: type[BaseFeed]):
        self._parsers[feed_type] = parser

    def get_parser_initial_data(self, feed: Feed) -> dict:
        parser = self._parsers[feed.type]
        return parser(feed, {}).data

    async def execute_parser(self, feed: Feed, data: dict) -> list[Item]:
        parser = self._parsers[feed.type]
        return await parser(feed, data).items
