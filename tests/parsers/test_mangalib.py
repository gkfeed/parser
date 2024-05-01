from app.serializers.feed import Feed
from app.parsers.mangalib import MangaLibFeed
from . import FakeDispatcher


async def test_insolarance_feed():
    dp = FakeDispatcher()

    feed = Feed(
        id=1,
        title="x",
        type="mangalib",
        url="https://mangalib.org/yuukoku-no-moriarty",
    )

    dp.register_parser("mangalib", MangaLibFeed)
    await dp.fetch_feed(feed)

    # test if parser actually works
    assert len(dp.items) != 0
