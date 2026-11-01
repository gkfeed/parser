from collections.abc import Mapping

from app.extensions.parsers.base import BaseFeed
from app.parsers import PARSERS
from app.serializers.feed import Feed, Item


def create_parser(
    feed: Feed, parsers: Mapping[str, type[BaseFeed]] = PARSERS
) -> BaseFeed:
    """Construct a parser using the runtime registry or an explicit override."""
    parser = parsers.get(feed.type)
    if parser is None:
        raise ValueError(f"No parser found for feed type: {feed.type}")
    return parser(feed)


class FeedParsingContext:
    """Compatibility adapter for existing integration fixtures.

    New callers should use create_parser. Keep this adapter until the existing
    FakeDispatcher fixture can migrate without changing its integration scope.
    """

    def __init__(self) -> None:
        self._parsers: dict[str, type[BaseFeed]] = {}

    def register_parser(self, feed_type: str, parser: type[BaseFeed]):
        self._parsers[feed_type] = parser

    def get_parser_initial_data(self, feed: Feed) -> dict:
        return {}

    async def execute_parser(self, feed: Feed, data: dict) -> list[Item]:
        if data:
            raise ValueError("Parser data is no longer supported; use typed fields")
        return await create_parser(feed, self._parsers).items
