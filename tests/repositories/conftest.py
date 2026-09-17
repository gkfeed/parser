from datetime import UTC, datetime

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base
from app.serializers.feed import Feed
from app.services.repositories.feed import FeedRepository
from app.services.repositories.feed_parser import FeedParserRepository
from app.services.repositories.item import ItemsRepository

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def session_factory():
    # Re-initialize engine and session_factory for each test loop
    engine = create_async_engine(TEST_DB_URL)

    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield session_factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
def feed_repository(session_factory):
    return FeedRepository(session_factory)


@pytest.fixture
def items_repository(session_factory):
    return ItemsRepository(session_factory)


@pytest.fixture
def feed_parser_repository(session_factory):
    return FeedParserRepository(session_factory)


@pytest.fixture
async def create_feed(feed_repository):
    feeds = []
    async def _create(title="Test Feed"):
        feed_data = Feed(
            id=0,
            title=title,
            url=f"https://test.com/{datetime.now(UTC).timestamp()}-{title}",
            type="test",
        )
        feed = await feed_repository.create(feed_data)
        feeds.append(feed)
        return feed
    
    yield _create
    
    # Cleanup
    for feed in feeds:
        await feed_repository.delete_by_id(feed.id)
