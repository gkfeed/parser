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
from app.core.parser_id import ParserId
from app.extensions.parsers.base import BaseFeed
from app.models import Base
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
            parsers={ParserId.WEB: BaseFeed},
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
