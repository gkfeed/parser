from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.configs import Data
from app.configs.selenium import get_driver
from app.models import Base
from app.serializers.feed import Feed
from app.services.container import Container
from app.services.repositories.feed import FeedRepository

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(autouse=True)
async def setup_db():
    # Re-initialize engine and session_factory for each test loop
    engine = create_async_engine(TEST_DB_URL)
    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Update container with the new session_factory bound to the current loop
    Container.setup(Data(selenium_web_driver=get_driver, db_session=session_factory))

    yield

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def create_feed():
    feeds = []
    async def _create(title="Test Feed"):
        feed_data = Feed(
            id=0,
            title=title,
            url=f"https://test.com/{datetime.now(UTC).timestamp()}-{title}",
            type="test",
        )
        feed = await FeedRepository.create(feed_data)
        feeds.append(feed)
        return feed
    
    yield _create
    
    # Cleanup
    for feed in feeds:
        await FeedRepository.delete_by_id(feed.id)
