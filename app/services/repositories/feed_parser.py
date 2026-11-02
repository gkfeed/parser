from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feed_parser import FeedParser

from ._base import BaseRepository
from .feed import _lock_feed_in_session


class FeedParserRepository(BaseRepository):
    async def get_by_feed_id(self, feed_id: int) -> FeedParser | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(FeedParser).where(FeedParser.feed_id == feed_id)
            )
            return result.scalar_one_or_none()

    async def upsert(self, feed_id: int, valid_for: datetime) -> FeedParser | None:
        async with self._session_factory() as session, session.begin():
            if not await _lock_feed_in_session(session, feed_id):
                return None
            return await self.upsert_in_session(session, feed_id, valid_for)

    @staticmethod
    async def upsert_in_session(
        session: AsyncSession, feed_id: int, valid_for: datetime
    ) -> FeedParser:
        """Write state within the caller's transaction and feed row lock."""
        statement = (
            insert(FeedParser)
            .values(feed_id=feed_id, valid_for=valid_for)
            .on_conflict_do_update(
                index_elements=[FeedParser.feed_id], set_={"valid_for": valid_for}
            )
            .returning(FeedParser)
        )
        result = await session.execute(
            statement, execution_options={"populate_existing": True}
        )
        return result.scalar_one()
