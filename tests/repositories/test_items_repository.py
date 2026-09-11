from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.models.item import Item as ItemModel
from app.models.item_hash import ItemHash
from app.serializers.feed import Feed, Item
from app.services.container import Container
from app.services.repositories.feed import FeedRepository
from app.services.repositories.item import ItemsRepository


@pytest.mark.asyncio
async def test_items_repository():
    # Setup feed
    feed_data = Feed(
        id=0,
        title="Item Test Feed",
        url=f"https://item-test.com/{datetime.now(UTC).timestamp()}",
        type="test",
    )
    feed = await FeedRepository.create(feed_data)

    now = datetime.now(UTC)
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
    
    now = datetime.now(UTC)
    item_link = f"https://dup-test.com/{now.timestamp()}"
    item_title = "Duplicate Item"
    
    # Manually insert two identical items
    async with Container.get_data().db_session() as session, session.begin():
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


@pytest.mark.asyncio
async def test_saving_item_and_hash_is_atomic(create_feed):
    feed = await create_feed("Atomic item test")
    item = Item(
        title="Item rejected by database",
        text="text",
        date=datetime.now(UTC),
        link="https://atomic.test/item",
        hash="atomic-hash",
    )

    async with Container.get_data().db_session() as session, session.begin():
        await session.execute(
            text(
                "CREATE TRIGGER reject_atomic_item BEFORE INSERT ON item "
                "WHEN NEW.link = 'https://atomic.test/item' "
                "BEGIN SELECT RAISE(ABORT, 'simulated item failure'); END"
            )
        )

    with pytest.raises(IntegrityError, match="simulated item failure"):
        await ItemsRepository.add_items_to_feed(feed, [item])

    async with Container.get_data().db_session() as session:
        item_count = await session.scalar(
            select(func.count())
            .select_from(ItemModel)
            .where(ItemModel.feed_id == feed.id)
        )
        hash_count = await session.scalar(
            select(func.count())
            .select_from(ItemHash)
            .where(ItemHash.feed_id == feed.id)
        )

    assert item_count == 0
    assert hash_count == 0

    async with Container.get_data().db_session() as session, session.begin():
        await session.execute(text("DROP TRIGGER reject_atomic_item"))

    saved_items = await ItemsRepository.add_items_to_feed(feed, [item])

    async with Container.get_data().db_session() as session:
        item_count = await session.scalar(
            select(func.count())
            .select_from(ItemModel)
            .where(ItemModel.feed_id == feed.id)
        )
        hash_count = await session.scalar(
            select(func.count())
            .select_from(ItemHash)
            .where(ItemHash.feed_id == feed.id)
        )

    assert saved_items == [item]
    assert item_count == 1
    assert hash_count == 1
