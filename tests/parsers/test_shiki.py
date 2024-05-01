from app.serializers.feed import Feed
from app.parsers.shiki import ShikiFeed
from . import FakeDispatcher


async def test_shiki_feed():
    dp = FakeDispatcher()

    feed = Feed(
        id=1,
        title="x",
        type="shiki",
        url="https://shikimori.one/animes/51180",
    )

    dp.register_parser("shiki", ShikiFeed)
    await dp.fetch_feed(feed)

    # test if parser actually works
    assert len(dp.items) != 0
