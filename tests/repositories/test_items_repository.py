import pytest
from datetime import datetime, timezone
from app.serializers.feed import Feed, Item
from app.services.repositories.feed import FeedRepository
from app.services.repositories.item import ItemsRepository
from app.models.item import Item as ItemModel
from app.services.container import Container


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


@pytest.mark.asyncio
async def test_items_repository_handles_existing_duplicates(create_feed):
    feed = await create_feed("Duplicate Test Feed")
    
    now = datetime.now(timezone.utc)
    item_link = f"https://dup-test.com/{now.timestamp()}"
    item_title = "Duplicate Item"
    
    # Manually insert two identical items
    async with Container.get_data().db_session() as session:
        async with session.begin():
            # Create two items manually to bypass repository checks
            item1 = ItemModel(
                feed_id=feed.id,
                title=item_title,
                text="text",
                date=now,
                link=item_link
            )
            item2 = ItemModel(
                feed_id=feed.id,
                title=item_title,
                text="text",
                date=now,
                link=item_link
            )
            session.add(item1)
            session.add(item2)
            
    # Prepare the item serializer object
    item_to_check = Item(
        title=item_title,
        text="text",
        date=now,
        link=item_link
    )
    
    # Try to add it again using Repository
    # This calls _check_if_exists which should not fail
    await ItemsRepository.add_items_to_feed(feed, [item_to_check])