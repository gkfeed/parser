from app.serializers.feed import Feed
from app.parsers.stories import InstagramStoriesFeed
from . import FakeDispatcher


async def test_stories_feed():
    dp = FakeDispatcher()

    feed = Feed(
        id=1,
        title="x",
        type="stories",
        url="https://www.instagram.com/buzova86",
    )

    dp.register_parser("stories", InstagramStoriesFeed)
    await dp.fetch_feed(feed)

    # test if parser actually works
    assert len(dp.items) != 0
