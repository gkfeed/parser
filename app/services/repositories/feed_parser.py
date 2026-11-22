from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.models.feed_parser import FeedParser

from ._base import BaseRepository


class FeedParserRepository(BaseRepository):
    async def get_by_feed_id(self, feed_id: int) -> FeedParser | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(FeedParser).where(FeedParser.feed_id == feed_id)
            )
            return result.scalar_one_or_none()

    async def upsert(self, feed_id: int, next_run_at: datetime) -> FeedParser:
        statement = (
            insert(FeedParser)
            .values(feed_id=feed_id, next_run_at=next_run_at)
            .on_conflict_do_update(
                index_elements=[FeedParser.feed_id],
                set_={FeedParser.next_run_at: next_run_at},
            )
            .returning(FeedParser)
        )
        async with self._session_factory() as session, session.begin():
            result = await session.execute(statement)
            return result.scalar_one()
