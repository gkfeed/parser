from dataclasses import dataclass
from enum import Enum

from app.core.parser_id import ParserId
from app.core.worker_kind import WorkerKind
from app.extensions.parsers.base import BaseFeed

from .anilibria import AnilibriaFeed
from .author_today import AuthorTodayFeed
from .hltv import HltvFeed
from .insolarance import InsolaranceFeed
from .instagram import InstagramFeed
from .kinogo import KinogoFeed
from .liquidpedia import LiquidpediaFeed
from .mangalib import MangaLibFeed
from .matreshka import MatreshkaFeed
from .onefootball import OneFootballFeed
from .pornhub import PornHubFeed
from .porno365 import Porno365Feed
from .ranobeme import RanobeMeFeed
from .reddit import RedditFeed
from .rezka import RezkaCollectionFeed, RezkaFeed
from .rtl import RTLSeriesFeed
from .sasflix import SasflixFeed
from .shiki import ShikiFeed
from .shiki_ongoing import ShikiOngoingFeed
from .spoti import SpotifyFeed, SpotifyPlaylistFeed
from .stories import InstagramStoriesFeed
from .tiktok import TikTokFeed
from .twitch import TwitchFeed
from .vk import VkFeed
from .vkvideo import VkVideoFeed
from .web import WebFeed
from .x import XFeed
from .youtube import YoutubeFeed
from .yummyanime import YummyAnimeFeed


@dataclass(frozen=True)
class ParserConfig:
    id: ParserId
    handler: type[BaseFeed]

    @property
    def worker_kind(self) -> WorkerKind:
        return self.handler.worker_kind


class Parser(Enum):
    WEB = ParserConfig(ParserId.WEB, WebFeed)
    TIKTOK = ParserConfig(ParserId.TIKTOK, TikTokFeed)
    KINOGO = ParserConfig(ParserId.KINOGO, KinogoFeed)
    TWITCH = ParserConfig(ParserId.TWITCH, TwitchFeed)
    YUMMYANIME = ParserConfig(ParserId.YUMMYANIME, YummyAnimeFeed)
    SHIKI = ParserConfig(ParserId.SHIKI, ShikiFeed)
    REDDIT = ParserConfig(ParserId.REDDIT, RedditFeed)
    VK = ParserConfig(ParserId.VK, VkFeed)
    VKVIDEO = ParserConfig(ParserId.VKVIDEO, VkVideoFeed)
    YT = ParserConfig(ParserId.YT, YoutubeFeed)
    RANOBE_ME = ParserConfig(ParserId.RANOBE_ME, RanobeMeFeed)
    SPOTI = ParserConfig(ParserId.SPOTI, SpotifyFeed)
    REZKA = ParserConfig(ParserId.REZKA, RezkaFeed)
    INST = ParserConfig(ParserId.INST, InstagramFeed)
    STORIES = ParserConfig(ParserId.STORIES, InstagramStoriesFeed)
    INSOLARANCE = ParserConfig(ParserId.INSOLARANCE, InsolaranceFeed)
    MANGALIB = ParserConfig(ParserId.MANGALIB, MangaLibFeed)
    X = ParserConfig(ParserId.X, XFeed)
    SPOTI_PLAYLIST = ParserConfig(ParserId.SPOTI_PLAYLIST, SpotifyPlaylistFeed)
    ONEFOOTBALL = ParserConfig(ParserId.ONEFOOTBALL, OneFootballFeed)
    RTL = ParserConfig(ParserId.RTL, RTLSeriesFeed)
    REZKA_COLLECTION = ParserConfig(ParserId.REZKA_COLLECTION, RezkaCollectionFeed)
    MATRESHKA = ParserConfig(ParserId.MATRESHKA, MatreshkaFeed)
    SHIKI_ONGOING = ParserConfig(ParserId.SHIKI_ONGOING, ShikiOngoingFeed)
    ANILIBRIA = ParserConfig(ParserId.ANILIBRIA, AnilibriaFeed)
    PORNHUB = ParserConfig(ParserId.PORNHUB, PornHubFeed)
    HLTV = ParserConfig(ParserId.HLTV, HltvFeed)
    LIQUIDPEDIA = ParserConfig(ParserId.LIQUIDPEDIA, LiquidpediaFeed)
    SASFLIX = ParserConfig(ParserId.SASFLIX, SasflixFeed)
    PORNO365 = ParserConfig(ParserId.PORNO365, Porno365Feed)
    AUTHOR_TODAY = ParserConfig(ParserId.AUTHOR_TODAY, AuthorTodayFeed)


# NOTE: inconsistent api
PARSERS: dict[ParserId, type[BaseFeed]] = {
    parser.value.id: parser.value.handler for parser in Parser
}
