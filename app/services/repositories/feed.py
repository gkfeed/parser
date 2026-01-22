from sqlalchemy import select, delete
from app.models.feed import Feed as _Feed
from app.serializers.feed import Feed
from ._base import BaseRepository


class FeedRepository(BaseRepository):
    @classmethod
    async def create(cls, item: Feed) -> Feed:
        async with cls._session_factory() as session:
            async with session.begin():
                _item = _Feed(title=item.title, url=item.url, type=item.type)
                session.add(_item)
                await session.flush()
                return await cls._unserialize(_item)

    @classmethod
    async def get_all(cls) -> list[Feed]:
        async with cls._session_factory() as session:
            result = await session.execute(select(_Feed))
            return [await cls._unserialize(f) for f in result.scalars().all()]

    @classmethod
    async def get_by_id(cls, id: int) -> Feed:
        async with cls._session_factory() as session:
            result = await session.execute(select(_Feed).where(_Feed.id == id))
            if not (item := result.scalar_one_or_none()):
                raise ValueError(f"No feed found by id: {id}")
            return await cls._unserialize(item)

    @classmethod
    async def delete_by_id(cls, id: int) -> None:
        async with cls._session_factory() as session:
            async with session.begin():
                await session.execute(delete(_Feed).where(_Feed.id == id))

    @classmethod
    async def _unserialize(cls, feed: _Feed) -> Feed:
        return Feed(id=feed.id, title=feed.title, url=feed.url, type=feed.type)
