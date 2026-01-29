from datetime import datetime

from sqlalchemy import select

from app.models.feed_parser import FeedParser
from ._base import BaseRepository


class FeedParserRepository(BaseRepository):
    @classmethod
    async def get_by_feed_id(cls, feed_id: int) -> FeedParser | None:
        async with cls._session_factory() as session:
            result = await session.execute(
                select(FeedParser).where(FeedParser.feed_id == feed_id)
            )
            return result.scalar_one_or_none()

    @classmethod
    async def upsert(cls, feed_id: int, valid_for: datetime) -> FeedParser:
        async with cls._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(FeedParser).where(FeedParser.feed_id == feed_id)
                )
                feed_parser = result.scalar_one_or_none()

                if feed_parser:
                    feed_parser.valid_for = valid_for
                else:
                    feed_parser = FeedParser(feed_id=feed_id, valid_for=valid_for)
                    session.add(feed_parser)
                
                await session.flush()
                return feed_parser
