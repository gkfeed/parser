from app.serializers.feed import Feed
from app.parsers.yummyanime import YummyAnimeFeed
from . import FakeDispatcher


async def test_yummyanime_feed():
    dp = FakeDispatcher()

    feed = Feed(
        id=1,
        title="x",
        type="yummyanime",
        url="https://yummy-anime.org/4769-dobro-pozhalovat-v-klass-prevoshodstva-3.html",
    )

    dp.register_parser("yummyanime", YummyAnimeFeed)
    await dp.fetch_feed(feed)

    # test if parser actually works
    assert len(dp.items) != 0
