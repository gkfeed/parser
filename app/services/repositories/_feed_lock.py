from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feed import Feed


async def lock_feed_in_session(session: AsyncSession, feed_id: int) -> bool:
    # Serialize parser results and prevent deletion until the commit completes.
    feed_id_found = await session.scalar(
        select(Feed.id).where(Feed.id == feed_id).with_for_update()
    )
    return feed_id_found is not None
