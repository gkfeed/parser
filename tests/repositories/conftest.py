import pytest
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.serializers.feed import Feed
from app.services.repositories.feed import FeedRepository
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


@pytest.fixture
async def create_feed():
    feeds = []
    async def _create(title="Test Feed"):
        feed_data = Feed(
            id=0,
            title=title,
            url=f"https://test.com/{datetime.now().timestamp()}-{title}",
            type="test",
        )
        feed = await FeedRepository.create(feed_data)
        feeds.append(feed)
        return feed
    
    yield _create
    
    # Cleanup
    for feed in feeds:
        try:
            await FeedRepository.delete_by_id(feed.id)
        except:
            pass
