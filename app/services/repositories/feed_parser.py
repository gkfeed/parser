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

    async def upsert(self, feed_id: int, valid_for: datetime) -> FeedParser:
        statement = (
            insert(FeedParser)
            .values(feed_id=feed_id, valid_for=valid_for)
            .on_conflict_do_update(
                index_elements=[FeedParser.feed_id], set_={"valid_for": valid_for}
            )
            .returning(FeedParser)
        )
        async with self._session_factory() as session, session.begin():
            result = await session.execute(statement)
            return result.scalar_one()
