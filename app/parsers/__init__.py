from dataclasses import dataclass
from enum import Enum

from app.core.worker_kind import WorkerKind
from app.extensions.parsers.base import BaseFeed
from .web import WebFeed
from .tiktok import TikTokFeed
from .kinogo import KinogoFeed
from .twitch import TwitchFeed
from .yummyanime import YummyAnimeFeed
from .shiki import ShikiFeed
from .reddit import RedditFeed
from .vk import VkFeed
from .youtube import AlternativeYoutubeFeed
from .ranobeme import RanobeMeFeed
from .spoti import SpotifyFeed, SpotifyPlaylistFeed
from .rezka import RezkaFeed
from .instagram import InstagramFeed
from .stories import InstagramStoriesFeed
from .insolarance import InsolaranceFeed
from .mangalib import MangaLibFeed
from .x import XFeed
from .onefootball import OneFootballFeed
from .rtl import RTLSeriesFeed
from .rezka import RezkaCollectionFeed
from .matreshka import MatreshkaFeed
from .shiki_ongoing import ShikiOngoingFeed
from .anilibria import AnilibriaFeed
from .pornhub import PornHubFeed
from .porno365 import Porno365Feed
from .hltv import HltvFeed
from .liquidpedia import LiquidpediaFeed
from .sasflix import SasflixFeed


@dataclass(frozen=True)
class ParserConfig:
    id: str
    handler: type[BaseFeed]

    @property
    def worker_kind(self) -> WorkerKind:
        return self.handler.worker_kind


class Parser(Enum):
    WEB = ParserConfig("web", WebFeed)
    TIKTOK = ParserConfig("tiktok", TikTokFeed)
    KINOGO = ParserConfig("kinogo", KinogoFeed)
    TWITCH = ParserConfig("twitch", TwitchFeed)
    YUMMYANIME = ParserConfig("yummyanime", YummyAnimeFeed)
    SHIKI = ParserConfig("shiki", ShikiFeed)
    REDDIT = ParserConfig("reddit", RedditFeed)
    VK = ParserConfig("vk", VkFeed)
    YT = ParserConfig("yt", AlternativeYoutubeFeed)
    RANOBE_ME = ParserConfig("ranobe.me", RanobeMeFeed)
    SPOTI = ParserConfig("spoti", SpotifyFeed)
    REZKA = ParserConfig("rezka", RezkaFeed)
    INST = ParserConfig("inst", InstagramFeed)
    STORIES = ParserConfig("stories", InstagramStoriesFeed)
    INSOLARANCE = ParserConfig("insolarance", InsolaranceFeed)
    MANGALIB = ParserConfig("mangalib", MangaLibFeed)
    X = ParserConfig("x", XFeed)
    SPOTI_PLAYLIST = ParserConfig("spoti:playlist", SpotifyPlaylistFeed)
    ONEFOOTBALL = ParserConfig("onefootball", OneFootballFeed)
    RTL = ParserConfig("rtl", RTLSeriesFeed)
    REZKA_COLLECTION = ParserConfig("rezka:collection", RezkaCollectionFeed)
    MATRESHKA = ParserConfig("matreshka", MatreshkaFeed)
    SHIKI_ONGOING = ParserConfig("shiki:ongoing", ShikiOngoingFeed)
    ANILIBRIA = ParserConfig("anilibria", AnilibriaFeed)
    PORNHUB = ParserConfig("pornhub", PornHubFeed)
    HLTV = ParserConfig("hltv", HltvFeed)
    LIQUIDPEDIA = ParserConfig("liquidpedia", LiquidpediaFeed)
    SASFLIX = ParserConfig("sasflix", SasflixFeed)
    PORNO365 = ParserConfig("porno365", Porno365Feed)


# NOTE: inconsistent api
PARSERS: dict[str, type[BaseFeed]] = {
    parser.value.id: parser.value.handler for parser in Parser
}
