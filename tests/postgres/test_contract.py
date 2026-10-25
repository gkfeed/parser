from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime, timedelta, timezone

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.run.check_schema_compatibility import (
    SchemaCompatibilityError,
    check_schema_compatibility,
)
from app.serializers.feed import Feed, FeedResult, Item
from app.services.broker import BrokerService
from app.services.repositories.feed import FeedRepository
from app.services.repositories.feed_parser import FeedParserRepository
from app.services.repositories.item import ItemsRepository

from .conftest import PostgresDatabase

pytestmark = pytest.mark.integration


@contextmanager
def recorded_statements(engine: AsyncEngine) -> Generator[list[str]]:
    statements = []

    def record(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)


async def test_eligibility_is_one_query(postgres_database: PostgresDatabase):
    db = postgres_database
    missing = await db.create_feed("missing")
    due = await db.create_feed("due")
    future = await db.create_feed("future")
    await db.create_feed("unsupported", "unsupported")
    now = datetime.now(UTC)
    feeds = FeedRepository(db.sessions)
    async with db.owner.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO public.feed_parser (feed_id, valid_for) "
                "VALUES (:id, :valid_for)"
            ),
            [
                {"id": due.id, "valid_for": now - timedelta(days=1)},
                {"id": future.id, "valid_for": now + timedelta(days=1)},
            ],
        )

    with recorded_statements(db.parser) as statements:
        eligible = await feeds.get_eligible({"test"})

    assert eligible == [missing, due]
    assert len(statements) == 1
    assert statements[0].lstrip().upper().startswith("SELECT ")
    assert await feeds.get_eligible(set()) == []


async def test_parser_role_has_no_schema_ownership(postgres_database: PostgresDatabase):
    async with postgres_database.parser.connect() as connection:
        privileges = (
            await connection.execute(
                text(
                    "SELECT current_user, "
                    "has_schema_privilege(current_user, 'public', 'CREATE'), "
                    "has_database_privilege(current_user, current_database(), 'CREATE'), "
                    "has_database_privilege(current_user, current_database(), 'TEMP'), "
                    "has_table_privilege(current_user, 'public.feed', 'INSERT'), "
                    "has_table_privilege(current_user, 'public.feed', 'UPDATE'), "
                    "has_table_privilege(current_user, 'public.item', 'DELETE')"
                )
            )
        ).one()
    assert tuple(privileges) == (
        "gkfeed_parser",
        False,
        False,
        False,
        False,
        False,
        False,
    )


async def test_schema_check_only_reads_external_registry(
    postgres_database: PostgresDatabase,
):
    with recorded_statements(postgres_database.parser) as statements:
        await check_schema_compatibility(postgres_database.parser)
    assert len(statements) == 1
    assert statements[0].lstrip().upper().startswith("SELECT ")


@pytest.mark.parametrize(
    ("version", "compatible"),
    [
        (None, False),
        ("20260904184132", False),
        ("20260904184133", True),
        ("99999999999999", True),
    ],
)
async def test_minimum_schema_version(
    postgres_database: PostgresDatabase, version, compatible
):
    async with postgres_database.owner.begin() as connection:
        await connection.execute(text("DELETE FROM public.schema_migrations"))
        if version is not None:
            await connection.execute(
                text(
                    "INSERT INTO public.schema_migrations (version) VALUES (:version)"
                ),
                {"version": version},
            )

    if not compatible:
        with pytest.raises(SchemaCompatibilityError, match="gkfeed/infra"):
            await check_schema_compatibility(postgres_database.parser)
        return
    await check_schema_compatibility(postgres_database.parser)


async def test_missing_registry_fails_without_creating_schema(
    postgres_database: PostgresDatabase,
):
    async with postgres_database.owner.begin() as connection:
        await connection.execute(text("DROP TABLE public.schema_migrations"))

    with pytest.raises(SchemaCompatibilityError, match="gkfeed/infra") as error:
        await check_schema_compatibility(postgres_database.parser)
    assert isinstance(error.value.__cause__, SQLAlchemyError)
    async with postgres_database.owner.connect() as connection:
        assert (
            await connection.scalar(
                text("SELECT to_regclass('public.schema_migrations')")
            )
            is None
        )


@asynccontextmanager
async def result_broker(
    db: PostgresDatabase, result: FeedResult, *, delete_feed: bool = False
) -> AsyncGenerator[BrokerService]:
    async def enqueue(request):
        payload = await request.json()
        feed = Feed.model_validate_json(payload["data"][0])
        assert payload["function"] == f"gkfeed.process_feed_{feed.type}"
        if delete_feed:
            async with db.owner.begin() as connection:
                await connection.execute(
                    text("DELETE FROM public.feed WHERE id = :id"), {"id": feed.id}
                )
        return web.json_response({"task_id": str(feed.id)})

    async def completed(_request):
        return web.json_response(
            {"status": "completed", "result": result.model_dump_json()}
        )

    app = web.Application()
    app.router.add_post("/enqueue", enqueue)
    app.router.add_get("/result/{task_id}", completed)
    async with TestServer(app) as server:
        yield BrokerService(str(server.make_url("/")))


def feed_result() -> FeedResult:
    return FeedResult(
        items=[
            Item(
                title="PostgreSQL contract",
                text="A complete parser result",
                date=datetime(2026, 9, 4, 12, 30, tzinfo=timezone(timedelta(hours=3))),
                link="https://example.com/item",
                hash="postgres-contract-item",
            )
        ]
    )


async def persisted_counts(db: PostgresDatabase) -> tuple[int, int, int]:
    async with db.owner.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT (SELECT count(*) FROM public.item), "
                    "(SELECT count(*) FROM public.item_hash), "
                    "(SELECT count(*) FROM public.feed_parser)"
                )
            )
        ).one()
    return tuple(row)


async def test_dispatch_persists_result_with_parser_permissions(
    postgres_database: PostgresDatabase,
):
    db = postgres_database
    feed = await db.create_feed("success")
    result = feed_result()
    async with result_broker(db, result) as broker:
        await db.dispatcher(broker).dispatch()

    assert await persisted_counts(db) == (1, 1, 1)
    stored = await ItemsRepository(db.sessions).get_all(feed)
    assert len(stored) == 1
    assert stored[0].date == result.items[0].date
    assert stored[0].text == result.items[0].text
    async with db.owner.connect() as connection:
        stored_hash = (
            await connection.execute(text("SELECT hash, feed_id FROM public.item_hash"))
        ).one()
    assert tuple(stored_hash) == (result.items[0].hash, feed.id)
    schedules = FeedParserRepository(db.sessions)
    state = await schedules.get_by_feed_id(feed.id)
    assert state is not None
    assert state.valid_for > datetime.now(UTC)

    # Simulate another due cycle to exercise hash deduplication and state upsert.
    await schedules.upsert(feed.id, datetime.now(UTC) - timedelta(days=1))
    async with result_broker(db, result) as broker:
        await db.dispatcher(broker).dispatch()
    assert await persisted_counts(db) == (1, 1, 1)

    async with db.owner.begin() as connection:
        await connection.execute(
            text("DELETE FROM public.feed WHERE id = :id"), {"id": feed.id}
        )
    assert await persisted_counts(db) == (0, 0, 0)


async def test_failed_state_write_rolls_back_result_and_can_retry(
    postgres_database: PostgresDatabase,
):
    db = postgres_database
    feed = await db.create_feed("rollback")
    items = feed_result().items
    valid_for = datetime.now(UTC) + timedelta(days=1)
    repository = ItemsRepository(db.sessions)
    async with db.owner.begin() as connection:
        await connection.execute(
            text(
                "ALTER TABLE public.feed_parser ADD CONSTRAINT reject_test_result "
                "CHECK (valid_for < TIMESTAMPTZ '2000-01-01 00:00:00+00')"
            )
        )

    with pytest.raises(IntegrityError, match="reject_test_result"):
        await repository.save_parser_result(feed, items, valid_for)
    assert await persisted_counts(db) == (0, 0, 0)

    async with db.owner.begin() as connection:
        await connection.execute(
            text("ALTER TABLE public.feed_parser DROP CONSTRAINT reject_test_result")
        )
    await repository.save_parser_result(feed, items, valid_for)
    assert await persisted_counts(db) == (1, 1, 1)


async def test_result_for_deleted_feed_is_discarded(
    postgres_database: PostgresDatabase,
):
    db = postgres_database
    await db.create_feed("deleted")
    async with result_broker(db, feed_result(), delete_feed=True) as broker:
        await db.dispatcher(broker).dispatch()
    assert await persisted_counts(db) == (0, 0, 0)
    assert await FeedRepository(db.sessions).get_all() == []


async def test_empty_result_advances_schedule(postgres_database: PostgresDatabase):
    db = postgres_database
    feed = await db.create_feed("empty")
    async with result_broker(db, FeedResult(items=[])) as broker:
        await db.dispatcher(broker).dispatch()
    assert await persisted_counts(db) == (0, 0, 1)
    schedule = await FeedParserRepository(db.sessions).get_by_feed_id(feed.id)
    assert schedule is not None
    assert schedule.valid_for > datetime.now(UTC)
