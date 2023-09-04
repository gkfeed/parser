from abc import abstractmethod
from typing import TypeVar

from app.serializers.feed import Feed, Item


class BaseFeed:
    def __init__(self, feed: Feed) -> None:
        self.feed = feed

    @property
    @abstractmethod
    async def items(self) -> list[Item]:
        pass


TFeedParser = TypeVar("TFeedParser", bound=BaseFeed)  # FIXME: deprecated
