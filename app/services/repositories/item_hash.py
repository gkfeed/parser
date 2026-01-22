from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item_hash import ItemHash
from ._base import BaseRepository


class ItemsHashRepository(BaseRepository):
    @classmethod
    async def contains(cls, hash: str, feed_id: int) -> bool:
        async with cls._session_factory() as session:
            async with session.begin():
                stmt = select(ItemHash).where(
                    ItemHash.hash == hash, ItemHash.feed_id == feed_id
                )
                result = await session.execute(stmt)
                if result.scalars().first() is not None:
                    return True

                return await cls._handle_lazy_migration(session, hash, feed_id)

    @classmethod
    async def _handle_lazy_migration(
        cls, session: AsyncSession, hash: str, feed_id: int
    ) -> bool:
        stmt = select(ItemHash).where(ItemHash.hash == hash, ItemHash.feed_id.is_(None))
        result = await session.execute(stmt)
        item = result.scalars().first()
        if item is not None:
            item.feed_id = feed_id
            return True

        return False

    @classmethod
    async def save(cls, hash: str, feed_id: int):
        async with cls._session_factory() as session:
            async with session.begin():
                item_hash = ItemHash(hash=hash, feed_id=feed_id)
                session.add(item_hash)
