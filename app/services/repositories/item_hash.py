from sqlalchemy import select
from app.models.item_hash import ItemHash
from ._base import BaseRepository


class ItemsHashRepository(BaseRepository):
    @classmethod
    async def contains(cls, hash: str) -> bool:
        async with cls._session_factory() as session:
            stmt = select(ItemHash).where(ItemHash.hash == hash)
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None

    @classmethod
    async def save(cls, hash: str):
        async with cls._session_factory() as session:
            async with session.begin():
                item_hash = ItemHash(hash=hash)
                session.add(item_hash)