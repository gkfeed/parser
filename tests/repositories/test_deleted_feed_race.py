import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from app.models import Base
from app.models.feed_parser import FeedParser
from app.models.item import Item as ItemModel
from app.models.item_hash import ItemHash
from app.serializers.feed import Feed, Item
from app.services.repositories.feed import FeedRepository
from app.services.repositories.feed_parser import FeedParserRepository
from app.services.repositories.item import ItemsRepository

pytestmark = pytest.mark.integration


@pytest.fixture
async def race_database():
    schema = f"deleted_feed_{uuid4().hex}"
    engine = create_async_engine(
        os.environ["PARSER_RESULT_TEST_DB_URL"],
        connect_args={"server_settings": {"search_path": schema}},
    )
    async with engine.begin() as connection:
        await connection.execute(CreateSchema(schema))
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield engine, async_sessionmaker(engine, expire_on_commit=False)
    finally:
        async with engine.begin() as connection:
            await connection.execute(DropSchema(schema, cascade=True))
        await engine.dispose()


async def wait_for_database_barrier(engine, lock_id):
    async with asyncio.timeout(5), engine.connect() as connection:
        while not await connection.scalar(
            text(
                "SELECT EXISTS (SELECT FROM pg_locks WHERE locktype = 'advisory' "
                "AND objid = :lock_id AND NOT granted)"
            ),
            {"lock_id": lock_id},
        ):
            await asyncio.sleep(0.01)


async def check_result(task, table, unrelated_error):
    if unrelated_error:
        with pytest.raises(IntegrityError, match="other_child"):
            await task
        return
    result = await task
    assert result == ([] if table == "item" else None)


@pytest.mark.parametrize("table", ["item", "feed_parser"])
@pytest.mark.parametrize("unrelated_error", [False, True])
async def test_deletion_during_write_only_discards_feed_fk_errors(
    race_database, table, unrelated_error
):
    engine, session_factory = race_database
    feeds = FeedRepository(session_factory)
    feed = await feeds.create(
        Feed(id=0, title="Feed", url="https://test.invalid/feed", type="test")
    )
    lock_id = uuid4().int % 2_000_000_000 + 1
    async with engine.begin() as connection:
        if unrelated_error:
            await connection.execute(
                text("CREATE TABLE other_parent (id integer PRIMARY KEY)")
            )
            await connection.execute(
                text(
                    "CREATE TABLE other_child (id integer REFERENCES other_parent(id))"
                )
            )
        extra_statement = (
            "INSERT INTO other_child VALUES (1);" if unrelated_error else ""
        )
        await connection.execute(
            text(
                "CREATE FUNCTION pause_result() RETURNS trigger LANGUAGE plpgsql AS $$ "
                f"BEGIN PERFORM pg_advisory_xact_lock({lock_id}); {extra_statement} "
                "RETURN NEW; END $$"
            )
        )
        await connection.execute(
            text(
                f"CREATE TRIGGER pause_result BEFORE INSERT ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION pause_result()"
            )
        )

    if table == "item":
        item = Item(
            title="Item",
            text="text",
            date=datetime.now(UTC),
            link="https://test.invalid/item",
        )
        operation = ItemsRepository(session_factory).save_parser_result(
            feed, [item], datetime.now(UTC)
        )
    else:
        operation = FeedParserRepository(session_factory).upsert(
            feed.id, datetime.now(UTC)
        )

    async with engine.connect() as barrier:
        await barrier.execute(text("SELECT pg_advisory_lock(:id)"), {"id": lock_id})
        task = asyncio.create_task(operation)
        try:
            await wait_for_database_barrier(engine, lock_id)
            await feeds.delete_by_id(feed.id)
        finally:
            await barrier.execute(
                text("SELECT pg_advisory_unlock(:id)"), {"id": lock_id}
            )
        await check_result(task, table, unrelated_error)

    async with session_factory() as session:
        for model in (ItemModel, ItemHash, FeedParser):
            assert await session.scalar(select(func.count()).select_from(model)) == 0
