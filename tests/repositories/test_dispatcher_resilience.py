import asyncio
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.dispatcher import Dispatcher
from app.extensions.parsers.base import BaseFeed
from app.models import Base
from app.run.dispatcher import dispatch_broker
from app.serializers.feed import Feed, FeedResult, Item
from app.services.broker import BrokerService
from app.services.repositories.feed import FeedRepository
from app.services.repositories.feed_parser import FeedParserRepository
from app.services.repositories.item import ItemsRepository


async def create_schema(engine: AsyncEngine, schema: str | None) -> None:
    async with engine.begin() as connection:
        if schema is not None:
            await connection.execute(text(f"CREATE SCHEMA {schema}"))
        await connection.run_sync(Base.metadata.create_all)


async def drop_schema(engine: AsyncEngine, schema: str | None) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        if schema is not None:
            await connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))


@pytest.fixture(
    params=["sqlite", pytest.param("postgresql", marks=pytest.mark.integration)],
)
async def session_factory(request):
    dialect = request.param
    schema = None
    url = "sqlite+aiosqlite:///:memory:"
    connect_args = {}
    if dialect == "postgresql":
        url = os.environ["PARSER_RESILIENCE_POSTGRES_URL"]
        schema = f"p06_{uuid4().hex}"
        connect_args = {"server_settings": {"search_path": schema}}
    engine = create_async_engine(url, connect_args=connect_args)
    await create_schema(engine, schema)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await drop_schema(engine, schema)
        await engine.dispose()


async def yield_control(_delay: float) -> None:
    await asyncio.sleep(0)


@dataclass
class LocalBroker:
    db: async_sessionmaker[AsyncSession]
    url: str = ""
    results: dict[int, Any] = field(default_factory=dict)
    requested: list[int] = field(default_factory=list)
    blocked_feed: int | None = None
    failing_feed: int | None = None
    peer_started: asyncio.Event = field(default_factory=asyncio.Event)
    release_peer: asyncio.Event = field(default_factory=asyncio.Event)

    async def enqueue(self, request: web.Request) -> web.Response:
        payload = await request.json()
        feed = Feed.model_validate_json(payload["data"][0])
        return web.json_response({"task_id": str(feed.id)})

    async def result(self, request: web.Request) -> web.Response:
        feed_id = int(request.match_info["task_id"])
        self.requested.append(feed_id)
        if feed_id == self.blocked_feed:
            self.peer_started.set()
            await self.release_peer.wait()
        if feed_id == self.failing_feed:
            await self.peer_started.wait()
        return web.json_response(
            self.results.get(
                feed_id,
                {
                    "status": "completed",
                    "result": FeedResult(items=[]).model_dump_json(),
                },
            )
        )

    def dispatcher(self) -> Dispatcher:
        return Dispatcher(
            broker=BrokerService(self.url),
            feed_repository=FeedRepository(self.db),
            feed_parser_repository=FeedParserRepository(self.db),
            items_repository=ItemsRepository(self.db),
            parsers={"test": BaseFeed},
            sleep=yield_control,
        )


@pytest.fixture
async def local_broker(session_factory):
    broker = LocalBroker(db=session_factory)
    app = web.Application()
    app.router.add_post("/enqueue", broker.enqueue)
    app.router.add_get("/result/{task_id}", broker.result)
    async with TestServer(app) as server:
        broker.url = str(server.make_url("/"))
        yield broker
        broker.release_peer.set()


async def execute_sql(db, statement: str) -> None:
    async with db() as session, session.begin():
        await session.execute(text(statement))


async def reject_schedule_writes(db) -> None:
    async with db() as session, session.begin():
        if session.get_bind().dialect.name == "postgresql":
            await session.execute(
                text(
                    "CREATE OR REPLACE FUNCTION reject_schedule() RETURNS trigger "
                    "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'database write rejected' "
                    "USING ERRCODE = '23514'; END $$"
                )
            )
            await session.execute(
                text(
                    "CREATE TRIGGER reject_schedule BEFORE INSERT ON feed_parser "
                    "FOR EACH ROW EXECUTE FUNCTION reject_schedule()"
                )
            )
            return
        await session.execute(
            text(
                "CREATE TRIGGER reject_schedule BEFORE INSERT ON feed_parser "
                "BEGIN SELECT RAISE(ABORT, 'database write rejected'); END"
            )
        )


async def allow_schedule_writes(db) -> None:
    async with db() as session, session.begin():
        statement = "DROP TRIGGER reject_schedule"
        if session.get_bind().dialect.name == "postgresql":
            statement += " ON feed_parser"
        await session.execute(text(statement))


@pytest.mark.parametrize(
    "broken_result",
    [
        {"status": "failed", "result": "parser crashed"},
        {"status": "completed", "result": "invalid json"},
        {"status": "completed", "result": '{"items": [{"title": "incomplete"}]}'},
        ["unexpected broker response"],
    ],
)
async def test_bad_feed_does_not_stop_peer(create_feed, local_broker, broken_result):
    broken = await create_feed("Broken feed")
    healthy = await create_feed("Healthy feed")
    item = Item(
        title="Healthy item",
        text="text",
        date=datetime.now(UTC),
        link="https://example.test/healthy-item",
    )
    local_broker.results[broken.id] = broken_result
    local_broker.results[healthy.id] = {
        "status": "completed",
        "result": FeedResult(items=[item]).model_dump_json(),
    }
    before = datetime.now(UTC)

    await local_broker.dispatcher().dispatch()

    assert set(local_broker.requested) == {broken.id, healthy.id}
    assert [
        saved.title for saved in await ItemsRepository(local_broker.db).get_all(healthy)
    ] == [item.title]
    assert await ItemsRepository(local_broker.db).get_all(broken) == []
    failed_schedule = await FeedParserRepository(local_broker.db).get_by_feed_id(
        broken.id
    )
    healthy_schedule = await FeedParserRepository(local_broker.db).get_by_feed_id(
        healthy.id
    )
    assert failed_schedule is not None
    assert healthy_schedule is not None
    assert failed_schedule.valid_for.replace(tzinfo=UTC) >= before + timedelta(
        minutes=13
    )
    assert healthy_schedule.valid_for.replace(tzinfo=UTC) > before


async def test_database_failure_cancels_pending_peer(create_feed, local_broker):
    broken = await create_feed("Rejected result")
    peer = await create_feed("Pending peer")
    local_broker.failing_feed = broken.id
    local_broker.blocked_feed = peer.id
    await reject_schedule_writes(local_broker.db)

    with pytest.raises(ExceptionGroup) as failure:
        await asyncio.wait_for(local_broker.dispatcher().dispatch(), timeout=5)

    assert failure.value.subgroup(IntegrityError) is not None
    assert local_broker.peer_started.is_set()
    assert await FeedParserRepository(local_broker.db).get_by_feed_id(broken.id) is None
    assert await FeedParserRepository(local_broker.db).get_by_feed_id(peer.id) is None


async def test_failed_feed_schedule_database_error_stops_cycle(
    create_feed, local_broker
):
    feed = await create_feed("Broken feed")
    local_broker.results[feed.id] = {"status": "completed", "result": "invalid json"}
    await reject_schedule_writes(local_broker.db)

    with pytest.raises(ExceptionGroup) as failure:
        await local_broker.dispatcher().dispatch()

    assert failure.value.subgroup(IntegrityError) is not None
    assert await FeedParserRepository(local_broker.db).get_by_feed_id(feed.id) is None


async def test_database_backoff_repeats_and_resets_after_success(
    create_feed, local_broker
):
    feed = await create_feed("Retry feed")
    await reject_schedule_writes(local_broker.db)
    delays = []

    async def advance(delay: float) -> None:
        delays.append(delay)
        if len(delays) == 8:
            await allow_schedule_writes(local_broker.db)
        if len(delays) == 9:
            schedule = await FeedParserRepository(local_broker.db).get_by_feed_id(
                feed.id
            )
            assert schedule is not None
            await execute_sql(local_broker.db, "DELETE FROM feed_parser")
            await reject_schedule_writes(local_broker.db)
        if len(delays) == 10:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await dispatch_broker(local_broker.dispatcher(), sleep=advance)

    assert delays == [1, 2, 5, 10, 30, 60, 60, 60, 60, 1]
    assert len(local_broker.requested) == 10


async def test_database_read_failure_backs_off(local_broker):
    await execute_sql(local_broker.db, "ALTER TABLE feed RENAME TO unavailable_feed")
    delays = []

    async def stop_after_retry(delay: float) -> None:
        delays.append(delay)
        raise asyncio.CancelledError

    try:
        with pytest.raises(asyncio.CancelledError):
            await dispatch_broker(local_broker.dispatcher(), sleep=stop_after_retry)
    finally:
        await execute_sql(
            local_broker.db, "ALTER TABLE unavailable_feed RENAME TO feed"
        )

    assert delays == [1]
    assert local_broker.requested == []


async def test_database_outage_does_not_escalate_feed_retry(create_feed, local_broker):
    feed = await create_feed("Unavailable feed")
    local_broker.results[feed.id] = {"status": "completed", "result": "invalid json"}
    await reject_schedule_writes(local_broker.db)
    delays = []
    before = datetime.now(UTC)

    async def advance(delay: float) -> None:
        delays.append(delay)
        if len(delays) == 4:
            await allow_schedule_writes(local_broker.db)
        if len(delays) == 5:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await dispatch_broker(local_broker.dispatcher(), sleep=advance)

    after = datetime.now(UTC)
    schedule = await FeedParserRepository(local_broker.db).get_by_feed_id(feed.id)
    assert schedule is not None
    retry_at = schedule.valid_for.replace(tzinfo=UTC)
    assert before + timedelta(minutes=13.5) <= retry_at
    assert retry_at <= after + timedelta(minutes=16.5)
    assert delays == [1, 2, 5, 10, 60]


async def test_postgres_connection_loss_backs_off(local_broker):
    connections = []

    async def disconnect(_reader, writer):
        connections.append(writer)
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(disconnect, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    engine = create_async_engine(
        f"postgresql+asyncpg://test:test@127.0.0.1:{port}/unavailable"
    )
    db = async_sessionmaker(engine, expire_on_commit=False)
    dispatcher = Dispatcher(
        broker=BrokerService(local_broker.url),
        feed_repository=FeedRepository(db),
        feed_parser_repository=FeedParserRepository(db),
        items_repository=ItemsRepository(db),
        parsers={"test": BaseFeed},
        sleep=yield_control,
    )
    delays = []

    async def stop_after_two_retries(delay: float) -> None:
        delays.append(delay)
        if len(delays) == 2:
            raise asyncio.CancelledError

    try:
        with pytest.raises(asyncio.CancelledError):
            await dispatch_broker(dispatcher, sleep=stop_after_two_retries)
    finally:
        server.close()
        await server.wait_closed()
        await engine.dispose()

    assert delays == [1, 2]
    assert len(connections) == 2
    assert local_broker.requested == []


async def test_non_database_cycle_error_is_not_retried(create_feed, local_broker):
    await create_feed("Test feed")
    dispatcher = local_broker.dispatcher()

    async def invalid_start(_delay: float) -> None:
        raise RuntimeError("invalid cycle configuration")

    async def unexpected_retry(_delay: float) -> None:
        raise AssertionError("A non-database cycle failure must propagate")

    dispatcher.sleep = invalid_start
    with pytest.raises(ExceptionGroup) as failure:
        await dispatch_broker(dispatcher, sleep=unexpected_retry)

    assert failure.value.subgroup(RuntimeError) is not None
