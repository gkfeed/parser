from abc import abstractmethod

from app.serializers.feed import Feed, Item


class BaseFeed:
    def __init__(self, feed: Feed, data: dict) -> None:
        self.feed = feed
        self.data = data

    @property
    @abstractmethod
    async def items(self) -> list[Item]:
        pass
