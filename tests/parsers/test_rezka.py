from app.serializers.feed import Feed
from app.parsers.rezka import RezkaFeed
from . import FakeDispatcher


async def test_rezka_feed():
    dp = FakeDispatcher()

    feed = Feed(
        id=1,
        title="x",
        type="rezka",
        url="https://hdrezka.me/series/drama/63941-slovo-pacana-krov-na-asfalte-2023.html",
    )

    dp.register_parser("rezka", RezkaFeed)
    await dp.fetch_feed(feed)

    # test if parser actually works
    assert len(dp.items) != 0
