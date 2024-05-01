import pytest

from app.serializers.feed import Feed
from app.parsers.tiktok import TikTokFeed
from . import FakeDispatcher


@pytest.mark.skip(reason="its not work")
async def test_tiktok_feed():
    dp = FakeDispatcher()

    feed = Feed(
        id=1,
        title="x",
        type="tiktok",
        url="https://www.tiktok.com/@sendependa_dio",
    )

    dp.register_parser("tiktok", TikTokFeed)

    await dp.fetch_feed(feed)

    assert len(dp.items) != 0
