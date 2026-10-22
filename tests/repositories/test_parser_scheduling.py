from datetime import UTC, datetime, timedelta
from functools import partial

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from sqlalchemy import text

from app.core.dispatcher import Dispatcher
from app.extensions.parsers.base import BaseFeed
from app.extensions.parsers.cache import CacheFeedExtension
from app.parsers import Parser
from app.serializers.feed import FeedFailure, FeedResult, Item
from app.services.broker import BrokerService
from app.services.repositories.feed import FeedRepository
from app.services.repositories.feed_parser import FeedParserRepository
from app.services.repositories.item import ItemsRepository


@pytest.fixture
async def broker_boundary():
    payload = {"status": "completed", "result": FeedResult(items=[]).model_dump_json()}
    submitted = []

    async def enqueue(request):
        submitted.append(await request.json())
        return web.json_response({"task_id": str(len(submitted))})

    async def result(request):
        return web.json_response(payload)

    app = web.Application()
    app.router.add_post("/enqueue", enqueue)
    app.router.add_get("/result/{task_id}", result)
    async with TestServer(app) as server:
        yield BrokerService(str(server.make_url("/"))), payload, submitted


@pytest.fixture
def dispatcher_factory(broker_boundary, session_factory):
    return partial(
        Dispatcher,
        broker=broker_boundary[0],
        feed_repository=FeedRepository(session_factory),
        feed_parser_repository=FeedParserRepository(session_factory),
        items_repository=ItemsRepository(session_factory),
    )


def make_item():
    return Item(
        title="Scheduled item",
        text="Item body",
        date=datetime.now(UTC),
        link="https://example.com/item",
        hash="scheduled-item",
    )


@pytest.mark.parametrize("has_items", [False, True], ids=["empty", "success"])
@pytest.mark.parametrize(
    "handler, empty_delay, success_delay",
    [
        (BaseFeed, timedelta(hours=1), timedelta(days=1)),
        (CacheFeedExtension, timedelta(minutes=5), timedelta(hours=1)),
        (Parser.ANILIBRIA.value.handler, timedelta(seconds=5), timedelta(days=1)),
        (Parser.TIKTOK.value.handler, timedelta(minutes=5), timedelta(days=1)),
        (Parser.INST.value.handler, timedelta(minutes=5), timedelta(weeks=1)),
    ],
    ids=["base", "cache", "custom", "inherited", "instagram"],
)
async def test_dispatch_schedules_results(
    create_feed,
    broker_boundary,
    dispatcher_factory,
    feed_repository,
    feed_parser_repository,
    items_repository,
    handler,
    empty_delay,
    success_delay,
    has_items,
):
    feed = await create_feed()
    _, payload, submitted = broker_boundary
    items = [make_item()] if has_items else []
    payload["result"] = FeedResult(items=items).model_dump_json()
    dispatcher = dispatcher_factory(parsers={feed.type: handler})

    before = datetime.now(UTC)
    await dispatcher.dispatch()
    after = datetime.now(UTC)

    schedule = await feed_parser_repository.get_by_feed_id(feed.id)
    assert schedule is not None
    delay = success_delay if has_items else empty_delay
    assert before + delay <= schedule.next_run_at.replace(tzinfo=UTC) <= after + delay
    saved = await items_repository.get_all(feed)
    assert [item.title for item in saved] == [item.title for item in items]
    assert await feed_repository.get_eligible({feed.type}) == []
    await dispatcher.dispatch()
    assert len(submitted) == 1


async def test_known_items_still_use_success_delay(
    create_feed,
    broker_boundary,
    dispatcher_factory,
    feed_parser_repository,
    items_repository,
):
    feed = await create_feed()
    _, payload, _ = broker_boundary
    item = make_item()
    await items_repository.add_items_to_feed(feed, [item])
    payload["result"] = FeedResult(items=[item]).model_dump_json()
    dispatcher = dispatcher_factory(parsers={feed.type: CacheFeedExtension})

    before = datetime.now(UTC)
    await dispatcher.dispatch()
    after = datetime.now(UTC)

    schedule = await feed_parser_repository.get_by_feed_id(feed.id)
    assert schedule is not None
    delay = timedelta(hours=1)
    assert before + delay <= schedule.next_run_at.replace(tzinfo=UTC) <= after + delay
    assert len(await items_repository.get_all(feed)) == 1


@pytest.mark.parametrize("has_items", [False, True], ids=["empty", "success"])
@pytest.mark.parametrize("retry_delay", [timedelta(days=3), -timedelta(days=1)])
async def test_parser_retry_overrides_policy(
    create_feed,
    broker_boundary,
    dispatcher_factory,
    feed_parser_repository,
    has_items,
    retry_delay,
):
    feed = await create_feed()
    _, payload, _ = broker_boundary
    retry_at = datetime.now(UTC) + retry_delay
    payload["result"] = FeedResult(
        items=[make_item()] if has_items else [], retry_at=retry_at
    ).model_dump_json()
    dispatcher = dispatcher_factory(parsers={feed.type: CacheFeedExtension})

    before = datetime.now(UTC)
    await dispatcher.dispatch()
    after = datetime.now(UTC)

    schedule = await feed_parser_repository.get_by_feed_id(feed.id)
    assert schedule is not None
    next_run_at = schedule.next_run_at.replace(tzinfo=UTC)
    if retry_delay > timedelta(0):
        assert next_run_at == retry_at
        return
    assert before + timedelta(seconds=1) <= next_run_at <= after + timedelta(seconds=1)


async def test_failure_backoff_progression_and_reset(
    create_feed, broker_boundary, dispatcher_factory, feed_parser_repository
):
    feed = await create_feed()
    _, payload, submitted = broker_boundary
    dispatcher = dispatcher_factory(parsers={feed.type: CacheFeedExtension})
    delays = [
        timedelta(minutes=15),
        timedelta(hours=1),
        timedelta(hours=6),
        timedelta(hours=24),
        timedelta(hours=24),
        timedelta(minutes=5),  # An empty success resets the failure count.
        timedelta(minutes=15),
    ]
    for index, delay in enumerate(delays):
        await feed_parser_repository.upsert(
            feed.id, next_run_at=datetime.now(UTC) - timedelta(days=1)
        )
        success = index == 5
        payload["status"] = "completed" if success else "failed"
        before = datetime.now(UTC)
        await dispatcher.dispatch()
        after = datetime.now(UTC)
        schedule = await feed_parser_repository.get_by_feed_id(feed.id)
        assert schedule is not None
        next_run_at = schedule.next_run_at.replace(tzinfo=UTC)
        assert before + delay * 0.9 <= next_run_at <= after + delay * 1.1
    assert len(submitted) == len(delays)


@pytest.mark.parametrize("explicit_retry", [False, True])
async def test_unavailable_feed_scheduling(
    create_feed,
    broker_boundary,
    dispatcher_factory,
    feed_parser_repository,
    explicit_retry,
):
    feed = await create_feed()
    _, payload, _ = broker_boundary
    retry_at = datetime.now(UTC) + timedelta(days=2) if explicit_retry else None
    payload.update(
        status="failed",
        result=FeedFailure(
            error_type="feed_unavailable", reason="source_down", retry_at=retry_at
        ).model_dump_json(),
    )
    dispatcher = dispatcher_factory(parsers={feed.type: CacheFeedExtension})
    before = datetime.now(UTC)
    await dispatcher.dispatch()
    after = datetime.now(UTC)
    schedule = await feed_parser_repository.get_by_feed_id(feed.id)
    assert schedule is not None
    next_run_at = schedule.next_run_at.replace(tzinfo=UTC)
    if explicit_retry:
        assert next_run_at == retry_at
        return
    delay = timedelta(minutes=15)
    assert before + delay * 0.9 <= next_run_at <= after + delay * 1.1


async def test_unclaimed_task_retries_after_one_minute(
    create_feed, broker_boundary, dispatcher_factory, feed_parser_repository
):
    feed = await create_feed()
    _, payload, _ = broker_boundary
    payload["status"] = "pending"
    dispatcher = dispatcher_factory(
        parsers={feed.type: BaseFeed}, broker_wait_timeout=0
    )
    before = datetime.now(UTC)
    await dispatcher.dispatch()
    after = datetime.now(UTC)
    schedule = await feed_parser_repository.get_by_feed_id(feed.id)
    assert schedule is not None
    delay = timedelta(minutes=1)
    assert before + delay <= schedule.next_run_at.replace(tzinfo=UTC) <= after + delay


async def test_next_run_at_reads_and_updates_legacy_column(
    create_feed, session_factory, feed_repository, feed_parser_repository
):
    feed = await create_feed()
    due = datetime.now(UTC) - timedelta(days=1)
    # Start with the deployed schema, independently of the ORM's table definition.
    async with session_factory() as session, session.begin():
        await session.execute(text("DROP TABLE feed_parser"))
        await session.execute(
            text(
                "CREATE TABLE feed_parser (feed_id INTEGER PRIMARY KEY "
                "REFERENCES feed(id) ON DELETE CASCADE, valid_for DATETIME NOT NULL)"
            )
        )
        await session.execute(
            text("INSERT INTO feed_parser (feed_id, valid_for) VALUES (:id, :due)"),
            {"id": feed.id, "due": due.isoformat(sep=" ")},
        )

    schedule = await feed_parser_repository.get_by_feed_id(feed.id)
    assert schedule is not None
    assert schedule.next_run_at.replace(tzinfo=UTC) == due
    assert schedule.valid_for == schedule.next_run_at
    assert await feed_repository.get_eligible({feed.type}) == [feed]

    future = datetime.now(UTC) + timedelta(days=1)
    updated = await feed_parser_repository.upsert(feed.id, next_run_at=future)
    assert updated.next_run_at == future
    assert await feed_repository.get_eligible({feed.type}) == []
    async with session_factory() as session:
        stored = await session.execute(
            text("SELECT valid_for FROM feed_parser WHERE feed_id = :id"),
            {"id": feed.id},
        )
        assert datetime.fromisoformat(stored.scalar_one()).replace(tzinfo=UTC) == future
