from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.models.item_hash import ItemHash
from app.utils.inject import inject


class ItemsHashRepository:
    @classmethod
    @inject({"session_factory": "db_session"})
    async def contains(
        cls, hash: str, session_factory: async_sessionmaker[AsyncSession]
    ) -> bool:
        async with session_factory() as session:
            stmt = select(ItemHash).where(ItemHash.hash == hash)
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None

    @classmethod
    @inject({"session_factory": "db_session"})
    async def save(cls, hash: str, session_factory: async_sessionmaker[AsyncSession]):
        async with session_factory() as session:
            async with session.begin():
                item_hash = ItemHash(hash=hash)
                session.add(item_hash)
