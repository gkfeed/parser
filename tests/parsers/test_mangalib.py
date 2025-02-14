from app.serializers.feed import Feed
from app.parsers.mangalib import MangaLibFeed
from . import FakeDispatcher


async def test_mangalib_feed():
    dp = FakeDispatcher()

    feed = Feed(
        id=1,
        title="x",
        type="mangalib",
        url="https://mangalib.org/ru/manga/4731--yuukoku-no-moriarty",
    )

    dp.register_parser("mangalib", MangaLibFeed)
    await dp.fetch_feed(feed)

    assert len(dp.items) != 0
