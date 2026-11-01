from enum import StrEnum


class ParserId(StrEnum):
    """Parser identifiers shared by storage, feed payloads, and task routing."""

    WEB = "web"
    TIKTOK = "tiktok"
    KINOGO = "kinogo"
    TWITCH = "twitch"
    YUMMYANIME = "yummyanime"
    SHIKI = "shiki"
    REDDIT = "reddit"
    VK = "vk"
    VKVIDEO = "vkvideo"
    YT = "yt"
    RANOBE_ME = "ranobe.me"
    SPOTI = "spoti"
    REZKA = "rezka"
    INST = "inst"
    STORIES = "stories"
    INSOLARANCE = "insolarance"
    MANGALIB = "mangalib"
    X = "x"
    SPOTI_PLAYLIST = "spoti:playlist"
    ONEFOOTBALL = "onefootball"
    RTL = "rtl"
    REZKA_COLLECTION = "rezka:collection"
    MATRESHKA = "matreshka"
    SHIKI_ONGOING = "shiki:ongoing"
    ANILIBRIA = "anilibria"
    PORNHUB = "pornhub"
    HLTV = "hltv"
    LIQUIDPEDIA = "liquidpedia"
    SASFLIX = "sasflix"
    PORNO365 = "porno365"
    AUTHOR_TODAY = "author.today"

    @property
    def task_name(self) -> str:
        return f"gkfeed.process_feed_{self.value}"
