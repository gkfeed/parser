from dataclasses import dataclass
from enum import Enum, StrEnum

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


class WorkerKind(StrEnum):
    LIGHT = "light"
    HEAVY = "heavy"


@dataclass(frozen=True)
class ParserConfig:
    id: str
    handler: type[BaseFeed]
    worker_kind: WorkerKind


class Parser(Enum):
    WEB = ParserConfig("web", WebFeed, WorkerKind.LIGHT)
    TIKTOK = ParserConfig("tiktok", TikTokFeed, WorkerKind.LIGHT)
    KINOGO = ParserConfig("kinogo", KinogoFeed, WorkerKind.LIGHT)
    TWITCH = ParserConfig("twitch", TwitchFeed, WorkerKind.LIGHT)
    YUMMYANIME = ParserConfig("yummyanime", YummyAnimeFeed, WorkerKind.HEAVY)
    SHIKI = ParserConfig("shiki", ShikiFeed, WorkerKind.LIGHT)
    REDDIT = ParserConfig("reddit", RedditFeed, WorkerKind.HEAVY)
    VK = ParserConfig("vk", VkFeed, WorkerKind.HEAVY)
    YT = ParserConfig("yt", AlternativeYoutubeFeed, WorkerKind.LIGHT)
    RANOBE_ME = ParserConfig("ranobe.me", RanobeMeFeed, WorkerKind.HEAVY)
    SPOTI = ParserConfig("spoti", SpotifyFeed, WorkerKind.HEAVY)
    REZKA = ParserConfig("rezka", RezkaFeed, WorkerKind.HEAVY)
    INST = ParserConfig("inst", InstagramFeed, WorkerKind.HEAVY)
    STORIES = ParserConfig("stories", InstagramStoriesFeed, WorkerKind.HEAVY)
    INSOLARANCE = ParserConfig("insolarance", InsolaranceFeed, WorkerKind.HEAVY)
    MANGALIB = ParserConfig("mangalib", MangaLibFeed, WorkerKind.HEAVY)
    X = ParserConfig("x", XFeed, WorkerKind.HEAVY)
    SPOTI_PLAYLIST = ParserConfig(
        "spoti:playlist", SpotifyPlaylistFeed, WorkerKind.HEAVY
    )
    ONEFOOTBALL = ParserConfig("onefootball", OneFootballFeed, WorkerKind.HEAVY)
    RTL = ParserConfig("rtl", RTLSeriesFeed, WorkerKind.HEAVY)
    REZKA_COLLECTION = ParserConfig(
        "rezka:collection", RezkaCollectionFeed, WorkerKind.HEAVY
    )
    MATRESHKA = ParserConfig("matreshka", MatreshkaFeed, WorkerKind.HEAVY)
    SHIKI_ONGOING = ParserConfig("shiki:ongoing", ShikiOngoingFeed, WorkerKind.HEAVY)
    ANILIBRIA = ParserConfig("anilibria", AnilibriaFeed, WorkerKind.HEAVY)
    PORNHUB = ParserConfig("pornhub", PornHubFeed, WorkerKind.LIGHT)
    HLTV = ParserConfig("hltv", HltvFeed, WorkerKind.LIGHT)
    LIQUIDPEDIA = ParserConfig("liquidpedia", LiquidpediaFeed, WorkerKind.LIGHT)
    SASFLIX = ParserConfig("sasflix", SasflixFeed, WorkerKind.HEAVY)
    PORNO365 = ParserConfig("porno365", Porno365Feed, WorkerKind.LIGHT)


# NOTE: inconsistant api
PARSERS: dict[str, type[BaseFeed]] = {
    parser.value.id: parser.value.handler for parser in Parser
}
