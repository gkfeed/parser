from typing import Type

from app.extentions.parsers.base import BaseFeed


class ParsersRegistrator:
    _parsers: dict[str, Type[BaseFeed]] = {}

    @classmethod
    def register_parser(cls, feed_type: str, parser: Type[BaseFeed]):
        cls._parsers[feed_type] = parser
