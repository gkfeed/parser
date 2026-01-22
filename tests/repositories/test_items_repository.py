import pytest
from datetime import datetime, timezone
from app.serializers.feed import Feed, Item
from app.services.repositories.feed import FeedRepository
from app.services.repositories.item import ItemsRepository


@pytest.mark.asyncio
async def test_items_repository():
    # Setup feed
    feed_data = Feed(
        id=0,
        title="Item Test Feed",
        url=f"https://item-test.com/{datetime.now().timestamp()}",
        type="test",
    )
    feed = await FeedRepository.create(feed_data)

    now = datetime.now(timezone.utc)
    items = [
        Item(title="Item 1", text="Text 1", date=now, link="https://link1.com"),
        Item(title="Item 2", text="Text 2", date=now, link="https://link2.com"),
    ]

    # Test Add Items
    await ItemsRepository.add_items_to_feed(feed, items)

    saved_items = await ItemsRepository.get_all(feed)
    assert len(saved_items) >= 2
    assert any(i.title == "Item 1" for i in saved_items)

    # Test Duplicate handling (should not add again)
    await ItemsRepository.add_items_to_feed(feed, items)
    saved_items_after = await ItemsRepository.get_all(feed)
    # Check that for this feed, count remains 2 (or whatever was added)
    assert len([i for i in saved_items_after if i.title in ["Item 1", "Item 2"]]) == 2

    # Clean up
    await FeedRepository.delete_by_id(feed.id)
