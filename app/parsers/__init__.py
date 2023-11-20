from typing import Type

from app.serializers.feed import Feed, Item
from app.extentions.parsers.base import BaseFeed
from .web import WebFeed
from .tiktok import TikTokFeed
from .kinogo import KinogoFeed
from .twitch import TwitchFeed
from .yummyanime import YummyAnimeFeed
from .shiki import ShikiFeed
from .reddit import RedditFeed
from .vk import VkFeed
from .youtube import YoutubeFeed
from .ranobeme import RanobeMeFeed
from .spoti import SpotifyFeed
from .rezka import RezkaFeed
from .instagram import InstagramFeed


_PARSERS: dict[str, Type[BaseFeed]] = {
    "web": WebFeed,
    "tiktok": TikTokFeed,
    "kinogo": KinogoFeed,
    "twitch": TwitchFeed,
    "yummyanime": YummyAnimeFeed,
    "shiki": ShikiFeed,
    "reddit": RedditFeed,
    "vk": VkFeed,
    "yt": YoutubeFeed,
    "ranobe.me": RanobeMeFeed,
    "spoti": SpotifyFeed,
    "rezka": RezkaFeed,
    "inst": InstagramFeed,
}


class FeedParser:
    _parsers = _PARSERS

    def __init__(self, feed: Feed):
        self.feed = feed
        if self.feed.type not in _PARSERS:
            raise ValueError(f"Unknown feed type: {self.feed.type}")

    async def parse(self) -> list[Item]:
        parser = self._parsers[self.feed.type]
        return await parser(self.feed).items
