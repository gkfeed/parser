from datetime import UTC, datetime

import pytest

from app.serializers.feed import Feed


@pytest.mark.asyncio
async def test_feed_repository(feed_repository):
    feed_data = Feed(
        id=0,
        title="Test Feed",
        url=f"https://test.com/{datetime.now(UTC).timestamp()}",
        type="test",
    )

    # Test Create
    created_feed = await feed_repository.create(feed_data)
    assert created_feed.id != 0
    assert created_feed.title == "Test Feed"

    # Test Get All
    all_feeds = await feed_repository.get_all()
    assert any(f.id == created_feed.id for f in all_feeds)

    # Test Get By ID
    found_feed = await feed_repository.get_by_id(created_feed.id)
    assert found_feed.title == "Test Feed"

    # Clean up
    await feed_repository.delete_by_id(created_feed.id)
