from sqlalchemy import delete, select

from app.models.feed import Feed as _Feed
from app.serializers.feed import Feed

from ._base import BaseRepository


class FeedRepository(BaseRepository):
    async def create(self, item: Feed) -> Feed:
        async with self._session_factory() as session, session.begin():
            _item = _Feed(title=item.title, url=item.url, type=item.type)
            session.add(_item)
            await session.flush()
            return await self._unserialize(_item)

    async def get_all(self) -> list[Feed]:
        async with self._session_factory() as session:
            result = await session.execute(select(_Feed))
            return [await self._unserialize(f) for f in result.scalars().all()]

    async def get_by_id(self, id: int) -> Feed:
        async with self._session_factory() as session:
            result = await session.execute(select(_Feed).where(_Feed.id == id))
            if not (item := result.scalar_one_or_none()):
                raise ValueError(f"No feed found by id: {id}")
            return await self._unserialize(item)

    async def delete_by_id(self, id: int) -> None:
        async with self._session_factory() as session, session.begin():
            await session.execute(delete(_Feed).where(_Feed.id == id))

    async def _unserialize(self, feed: _Feed) -> Feed:
        return Feed(id=feed.id, title=feed.title, url=feed.url, type=feed.type)
