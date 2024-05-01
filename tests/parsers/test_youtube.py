from app.serializers.feed import Feed
from app.parsers.youtube import YoutubeFeed
from . import FakeDispatcher


async def test_youtube_feed():
    dp = FakeDispatcher()

    feed = Feed(
        id=1,
        title="x",
        type="yt",
        url="https://www.youtube.com/channel/UCJM8s_4MRZF7CgIxM84d0cg",
    )

    dp.register_parser("yt", YoutubeFeed)
    await dp.fetch_feed(feed)

    # test if parser actually works
    assert len(dp.items) != 0
