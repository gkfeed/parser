from app.serializers.feed import Feed
from app.parsers.web import WebFeed
from . import FakeDispatcher


async def test_web_feed():
    dp = FakeDispatcher()

    feed = Feed(
        id=1,
        title="x",
        type="web",
        url="https://beardycast.com/feed/",
    )

    dp.register_parser("web", WebFeed)
    await dp.fetch_feed(feed)

    # test if parser actually works
    assert len(dp.items) != 0
