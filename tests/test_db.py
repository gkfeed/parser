import pytest
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.serializers.feed import Feed, Item
from app.services.repositories.feed import FeedRepository
from app.services.repositories.item import ItemsRepository
from app.configs.env import DB_URL
from app.services.container import Container
from app.configs import Data
from app.configs.selenium import get_driver


@pytest.fixture(autouse=True)
async def setup_db():
    # Re-initialize engine and session_factory for each test loop
    engine = create_async_engine(DB_URL)
    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    # Update container with the new session_factory bound to the current loop
    Container.setup(Data(selenium_web_driver=get_driver, db_session=session_factory))

    yield

    await engine.dispose()


@pytest.mark.asyncio
async def test_feed_repository():
    feed_data = Feed(
        id=0,
        title="Test Feed",
        url=f"https://test.com/{datetime.now().timestamp()}",
        type="test",
    )

    # Test Create
    created_feed = await FeedRepository.create(feed_data)
    assert created_feed.id != 0
    assert created_feed.title == "Test Feed"

    # Test Get All
    all_feeds = await FeedRepository.get_all()
    assert any(f.id == created_feed.id for f in all_feeds)

    # Test Get By ID
    found_feed = await FeedRepository.get_by_id(created_feed.id)
    assert found_feed.title == "Test Feed"

    # Clean up
    await FeedRepository.delete_by_id(created_feed.id)


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
async def test_item_hash_repository():
    from app.services.repositories.item_hash import ItemsHashRepository

    test_hash = f"test-hash-{datetime.now().timestamp()}"

    # Test contains (should be false)
    assert not await ItemsHashRepository.contains(test_hash)

    # Test save
    await ItemsHashRepository.save(test_hash)

    # Test contains (should be true)
    assert await ItemsHashRepository.contains(test_hash)
