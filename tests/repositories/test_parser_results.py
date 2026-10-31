import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from sqlalchemy import event, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.dispatcher import Dispatcher
from app.extensions.parsers.base import BaseFeed
from app.models import Base
from app.models.feed import Feed as FeedModel
from app.models.feed_parser import FeedParser
from app.models.item import Item as ItemModel
from app.models.item_hash import ItemHash
from app.serializers.feed import Feed, FeedResult, Item
from app.services.broker import BrokerService
from app.services.repositories.feed import FeedRepository
from app.services.repositories.feed_parser import FeedParserRepository
from app.services.repositories.item import ItemsRepository


@pytest.fixture(
    params=["sqlite", pytest.param("postgresql", marks=pytest.mark.integration)]
)
async def result_engine(request):
    schema = f"parser_results_{uuid4().hex}"
    if request.param == "postgresql":
        url = os.environ["PARSER_RESULT_TEST_DB_URL"]
        engine = create_async_engine(
            url, connect_args={"server_settings": {"search_path": schema}}
        )
    else:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")

        @event.listens_for(engine.sync_engine, "connect")
        def enable_foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        if request.param == "postgresql":
            await connection.execute(CreateSchema(schema))
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await drop_result_tables(engine, schema)
        await engine.dispose()


async def drop_result_tables(engine, schema):
    async with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            await connection.execute(DropSchema(schema, cascade=True))
            return
        await connection.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def result_db(result_engine):
    return async_sessionmaker(result_engine, expire_on_commit=False)


@pytest.fixture
async def result_feed(result_db):
    return await FeedRepository(result_db).create(
        Feed(id=0, title="Atomic results", url="https://atomic.test/feed", type="test")
    )


def make_item(suffix="first", hash_value="result-hash"):
    return Item(
        title=f"Item {suffix}",
        text="text",
        date=datetime.now(UTC),
        link=f"https://atomic.test/{suffix}",
        hash=hash_value,
    )


async def row_counts(result_db, feed):
    async with result_db() as session:
        counts = []
        for model in (ItemModel, ItemHash, FeedParser):
            counts.append(
                await session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.feed_id == feed.id)
                )
            )
    return counts


async def reject_writes(result_db, table):
    # Fail at a real SQL boundary, including the final parser-state write.
    async with result_db() as session, session.begin():
        if session.get_bind().dialect.name == "postgresql":
            await session.execute(
                text(
                    "CREATE FUNCTION reject_result() RETURNS trigger LANGUAGE plpgsql AS $$ "
                    "BEGIN RAISE EXCEPTION 'result write rejected' USING ERRCODE = '23514'; END $$"
                )
            )
            await session.execute(
                text(
                    f"CREATE TRIGGER reject_result BEFORE INSERT OR UPDATE ON {table} "
                    "FOR EACH ROW EXECUTE FUNCTION reject_result()"
                )
            )
            return
        await session.execute(
            text(
                f"CREATE TRIGGER reject_result BEFORE INSERT ON {table} "
                "BEGIN SELECT RAISE(ABORT, 'result write rejected'); END"
            )
        )


async def allow_writes(result_db, table):
    async with result_db() as session, session.begin():
        if session.get_bind().dialect.name == "postgresql":
            await session.execute(text(f"DROP TRIGGER reject_result ON {table}"))
            await session.execute(text("DROP FUNCTION reject_result()"))
            return
        await session.execute(text("DROP TRIGGER reject_result"))


@pytest.mark.parametrize("table", ["item", "item_hash", "feed_parser"])
@pytest.mark.parametrize("existing_schedule", [False, True])
async def test_result_rolls_back_and_can_be_retried(
    result_db, result_feed, table, existing_schedule
):
    repository = ItemsRepository(result_db)
    schedules = FeedParserRepository(result_db)
    previous = datetime.now(UTC) - timedelta(days=1)
    valid_for = datetime.now(UTC) + timedelta(days=1)
    if existing_schedule:
        await schedules.upsert(result_feed.id, previous)
    await reject_writes(result_db, table)
    item = make_item()

    with pytest.raises(IntegrityError, match="result write rejected"):
        await repository.save_parser_result(result_feed, [item], valid_for)

    assert await row_counts(result_db, result_feed) == [0, 0, int(existing_schedule)]
    schedule = await schedules.get_by_feed_id(result_feed.id)
    if existing_schedule:
        assert schedule is not None
        assert schedule.valid_for.replace(tzinfo=UTC) == previous
    else:
        assert schedule is None

    await allow_writes(result_db, table)
    assert await repository.save_parser_result(result_feed, [item], valid_for) == [item]
    assert await repository.save_parser_result(result_feed, [item], valid_for) == []
    assert await row_counts(result_db, result_feed) == [1, 1, 1]
    schedule = await schedules.get_by_feed_id(result_feed.id)
    assert schedule is not None
    assert schedule.valid_for.replace(tzinfo=UTC) == valid_for


async def test_deleted_feed_discards_items_and_schedule(result_db, result_feed):
    await FeedRepository(result_db).delete_by_id(result_feed.id)

    assert (
        await ItemsRepository(result_db).save_parser_result(
            result_feed, [make_item()], datetime.now(UTC)
        )
        == []
    )
    assert (
        await FeedParserRepository(result_db).upsert(result_feed.id, datetime.now(UTC))
        is None
    )
    assert await row_counts(result_db, result_feed) == [0, 0, 0]


async def test_result_uses_feed_id_after_url_and_type_change(result_db, result_feed):
    async with result_db() as session, session.begin():
        await session.execute(
            update(FeedModel)
            .where(FeedModel.id == result_feed.id)
            .values(url="https://atomic.test/changed", type="changed")
        )
    item = make_item()
    assert await ItemsRepository(result_db).save_parser_result(
        result_feed, [item], datetime.now(UTC)
    ) == [item]
    assert await row_counts(result_db, result_feed) == [1, 1, 1]
    feed = await FeedRepository(result_db).get_by_id(result_feed.id)
    assert feed.url == "https://atomic.test/changed"
    assert feed.type == "changed"


async def test_empty_result_updates_schedule(result_db, result_feed):
    repository = ItemsRepository(result_db)
    await repository.save_parser_result(result_feed, [], datetime.now(UTC))
    valid_for = datetime.now(UTC) + timedelta(days=1)
    assert await repository.save_parser_result(result_feed, [], valid_for) == []
    assert await row_counts(result_db, result_feed) == [0, 0, 1]
    schedule = await FeedParserRepository(result_db).get_by_feed_id(result_feed.id)
    assert schedule is not None
    assert schedule.valid_for.replace(tzinfo=UTC) == valid_for


async def test_dispatch_rolls_back_then_retries_broker_result(result_db, result_feed):
    item = make_item()
    submitted = []

    async def enqueue(request):
        submitted.append(await request.json())
        return web.json_response({"task_id": "atomic-result"})

    async def result(request):
        return web.json_response(
            {
                "status": "completed",
                "result": FeedResult(items=[item]).model_dump_json(),
            }
        )

    app = web.Application()
    app.router.add_post("/enqueue", enqueue)
    app.router.add_get("/result/{task_id}", result)
    await reject_writes(result_db, "feed_parser")
    async with TestServer(app) as server:
        dispatcher = Dispatcher(
            broker=BrokerService(str(server.make_url("/"))),
            feed_parser_repository=FeedParserRepository(result_db),
            feed_repository=FeedRepository(result_db),
            items_repository=ItemsRepository(result_db),
            parsers={"test": BaseFeed},
        )
        with pytest.raises(ExceptionGroup) as caught:
            await dispatcher.dispatch()
        assert len(caught.value.exceptions) == 1
        assert isinstance(caught.value.exceptions[0], IntegrityError)
        assert await row_counts(result_db, result_feed) == [0, 0, 0]

        await allow_writes(result_db, "feed_parser")
        await dispatcher.dispatch()
        await dispatcher.dispatch()

    assert len(submitted) == 2
    assert await row_counts(result_db, result_feed) == [1, 1, 1]


@pytest.mark.integration
@pytest.mark.parametrize("result_engine", ["postgresql"], indirect=True)
async def test_concurrent_results_are_serialized(result_engine, result_db, result_feed):
    repository = ItemsRepository(result_db)
    item = make_item()
    valid_for = datetime.now(UTC) + timedelta(days=1)
    results = await asyncio.gather(
        repository.save_parser_result(result_feed, [item], valid_for),
        repository.save_parser_result(result_feed, [item], valid_for),
    )
    assert sorted(len(items) for items in results) == [0, 1]
    assert await row_counts(result_db, result_feed) == [1, 1, 1]


@pytest.mark.integration
@pytest.mark.parametrize("result_engine", ["postgresql"], indirect=True)
async def test_commit_failure_rolls_back_the_complete_result(result_db, result_feed):
    await reject_writes(result_db, "feed_parser")
    async with result_db() as session, session.begin():
        await session.execute(text("DROP TRIGGER reject_result ON feed_parser"))
        await session.execute(
            text(
                "CREATE CONSTRAINT TRIGGER reject_result AFTER INSERT OR UPDATE ON feed_parser "
                "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION reject_result()"
            )
        )
    repository = ItemsRepository(result_db)
    item = make_item()
    valid_for = datetime.now(UTC) + timedelta(days=1)
    with pytest.raises(IntegrityError, match="result write rejected"):
        await repository.save_parser_result(result_feed, [item], valid_for)
    assert await row_counts(result_db, result_feed) == [0, 0, 0]

    await allow_writes(result_db, "feed_parser")
    assert await repository.save_parser_result(result_feed, [item], valid_for) == [item]
    assert await row_counts(result_db, result_feed) == [1, 1, 1]


async def test_dispatch_discards_feed_deleted_while_broker_is_working(
    result_db, result_feed
):
    async def enqueue(request):
        # A separate connection can delete the feed while broker I/O is in progress.
        await FeedRepository(result_db).delete_by_id(result_feed.id)
        return web.json_response({"task_id": "deleted-feed"})

    async def result(request):
        return web.json_response(
            {
                "status": "completed",
                "result": FeedResult(items=[make_item()]).model_dump_json(),
            }
        )

    app = web.Application()
    app.router.add_post("/enqueue", enqueue)
    app.router.add_get("/result/{task_id}", result)
    async with TestServer(app) as server:
        dispatcher = Dispatcher(
            broker=BrokerService(str(server.make_url("/"))),
            feed_parser_repository=FeedParserRepository(result_db),
            feed_repository=FeedRepository(result_db),
            items_repository=ItemsRepository(result_db),
            parsers={"test": BaseFeed},
        )
        await dispatcher.dispatch()
    assert await row_counts(result_db, result_feed) == [0, 0, 0]
