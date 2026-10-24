from app.core.parser_id import ParserId
from app.extensions.parsers.base import BaseFeed
from app.serializers.feed import Feed, Item


class FeedParsingContext:
    def __init__(self) -> None:
        self._parsers: dict[ParserId, type[BaseFeed]] = {}

    def register_parser(self, parser_id: ParserId | str, parser: type[BaseFeed]):
        self._parsers[ParserId(parser_id)] = parser

    def get_parser_initial_data(self, feed: Feed) -> dict:
        parser = self._parsers[feed.type]
        return parser(feed, {}).data

    async def execute_parser(self, feed: Feed, data: dict) -> list[Item]:
        parser = self._parsers[feed.type]
        return await parser(feed, data).items
