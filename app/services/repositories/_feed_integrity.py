from collections.abc import Callable

from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feed import Feed


async def feed_exists(session: AsyncSession, feed_id: int) -> bool:
    return await session.scalar(select(Feed.id).where(Feed.id == feed_id)) is not None


async def deleted_feed_caused_error(
    session_factory: Callable[[], AsyncSession], feed_id: int, error: IntegrityError
) -> bool:
    """Recognize a feed foreign-key violation only after the failed transaction ends."""
    original = error.orig
    if original is None or getattr(original, "sqlstate", None) != "23503":
        return False
    cause = original.__cause__
    table = getattr(cause, "table_name", None)
    schema = getattr(cause, "schema_name", None)
    constraint = getattr(cause, "constraint_name", None)
    if (
        table not in {"item", "item_hash", "feed_parser"}
        or not schema
        or not constraint
    ):
        return False

    async with session_factory() as session:
        connection = await session.connection()
        foreign_keys = await connection.run_sync(
            lambda sync_connection: inspect(sync_connection).get_foreign_keys(
                table, schema=schema
            )
        )
        is_feed_key = any(
            key["name"] == constraint
            and key["constrained_columns"] == ["feed_id"]
            and key["referred_table"] == "feed"
            and key["referred_columns"] == ["id"]
            for key in foreign_keys
        )
        return is_feed_key and not await feed_exists(session, feed_id)
