from typing import Type

from app.extentions.parsers.base import BaseFeed
from .web import WebFeed
from .tiktok import TikTokFeed
from .kinogo import KinogoFeed
from .twitch import TwitchFeed
from .yummyanime import YummyAnimeFeed
from .shiki import ShikiFeed
from .reddit import RedditFeed
from .vk import VkFeed
from .youtube import YoutubeFeed, AlternativeYoutubeFeed
from .ranobeme import RanobeMeFeed
from .spoti import SpotifyFeed, SpotifyPlaylistFeed
from .rezka import RezkaFeed
from .instagram import InstagramFeed
from .stories import InstagramStoriesFeed
from .insolarance import InsolaranceFeed
from .mangalib import MangaLibFeed
from .x import XFeed
from .onefootball import OneFootballFeed
from .rtl import RTLSerieFeed
from .rezka import RezkaCollecionFeed
from .matreshka import MatreshkaFeed


PARSERS: dict[str, Type[BaseFeed]] = {
    "web": WebFeed,
    "tiktok": TikTokFeed,
    "kinogo": KinogoFeed,
    "twitch": TwitchFeed,
    "yummyanime": YummyAnimeFeed,
    "shiki": ShikiFeed,
    "reddit": RedditFeed,
    "vk": VkFeed,
    # "yt": YoutubeFeed,
    "yt": AlternativeYoutubeFeed,
    "ranobe.me": RanobeMeFeed,
    "spoti": SpotifyFeed,
    "rezka": RezkaFeed,
    "inst": InstagramFeed,
    "stories": InstagramStoriesFeed,
    "insolarance": InsolaranceFeed,
    "mangalib": MangaLibFeed,
    "x": XFeed,
    "spoti:playlist": SpotifyPlaylistFeed,
    "onefootball": OneFootballFeed,
    "rtl": RTLSerieFeed,
    "rezka:collection": RezkaCollecionFeed,
    "matreshka": MatreshkaFeed,
}
