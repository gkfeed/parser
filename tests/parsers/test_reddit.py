from app.serializers.feed import Feed
from app.parsers.reddit import RedditFeed
from . import FakeDispatcher


async def test_reddit_feed():
    dp = FakeDispatcher()
    feed = Feed(
        id=1,
        title="x",
        type="reddit",
        url="https://www.reddit.com/r/neovim",
    )

    dp.register_parser("reddit", RedditFeed)
    await dp.fetch_feed(feed)

    # test if parser actually works
    assert len(dp.items) != 0
