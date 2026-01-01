from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.models.feed import Feed as _Feed
from app.serializers.feed import Feed
from app.utils.inject import inject


class FeedRepository:
    @classmethod
    @inject({"session_factory": "db_session"})
    async def create(
        cls, item: Feed, session_factory: async_sessionmaker[AsyncSession]
    ) -> Feed:
        async with session_factory() as session:
            async with session.begin():
                _item = _Feed(title=item.title, url=item.url, type=item.type)
                session.add(_item)
                await session.flush()
                return await cls._unserialize(_item)

    @classmethod
    @inject({"session_factory": "db_session"})
    async def get_all(
        cls, session_factory: async_sessionmaker[AsyncSession]
    ) -> list[Feed]:
        async with session_factory() as session:
            result = await session.execute(select(_Feed))
            return [await cls._unserialize(f) for f in result.scalars().all()]

    @classmethod
    @inject({"session_factory": "db_session"})
    async def get_by_id(
        cls, id: int, session_factory: async_sessionmaker[AsyncSession]
    ) -> Feed:
        async with session_factory() as session:
            result = await session.execute(select(_Feed).where(_Feed.id == id))
            if not (item := result.scalar_one_or_none()):
                raise ValueError(f"No feed found by id: {id}")
            return await cls._unserialize(item)

    @classmethod
    @inject({"session_factory": "db_session"})
    async def delete_by_id(
        cls, id: int, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            async with session.begin():
                await session.execute(delete(_Feed).where(_Feed.id == id))

    @classmethod
    async def _unserialize(cls, feed: _Feed) -> Feed:
        return Feed(id=feed.id, title=feed.title, url=feed.url, type=feed.type)
