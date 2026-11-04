import json
from datetime import UTC, datetime, timedelta

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from pydantic import ValidationError
from sqlalchemy import select

from app.core.dispatcher import Dispatcher
from app.core.parser_id import ParserId
from app.extensions.parsers.base import BaseFeed
from app.models.feed import Feed as FeedModel
from app.serializers.feed import Feed, FeedResult
from app.services.broker import BrokerService


@pytest.mark.asyncio
async def test_feed_repository(feed_repository):
    feed_data = Feed(
        id=0,
        title="Test Feed",
        url=f"https://test.com/{datetime.now(UTC).timestamp()}",
        type=ParserId.WEB,
    )

    # Test Create
    created_feed = await feed_repository.create(feed_data)
    assert created_feed.id != 0
    assert created_feed.title == "Test Feed"

    # Test Get All
    all_feeds = await feed_repository.get_all()
    assert any(f.id == created_feed.id for f in all_feeds)

    # Test Get By ID
    found_feed = await feed_repository.get_by_id(created_feed.id)
    assert found_feed.title == "Test Feed"

    # Clean up
    await feed_repository.delete_by_id(created_feed.id)


@pytest.fixture
async def scheduled_feeds(feed_repository, feed_parser_repository):
    now = datetime.now(UTC)
    # TWITCH is valid but not configured in this dispatcher.
    cases = [
        ("future", ParserId.WEB, now + timedelta(days=1)),
        ("missing", ParserId.WEB, None),
        ("unconfigured-missing", ParserId.TWITCH, None),
        ("due", ParserId.WEB, now - timedelta(days=1)),
        ("unconfigured-due", ParserId.TWITCH, now - timedelta(days=1)),
        ("naive-due", ParserId.RANOBE_ME, now.replace(tzinfo=None) - timedelta(days=1)),
    ]
    feeds = {}
    for title, parser_type, valid_for in cases:
        feed = await feed_repository.create(
            Feed(
                id=0, title=title, url=f"https://example.com/{title}", type=parser_type
            )
        )
        feeds[title] = feed
        if valid_for is not None:
            await feed_parser_repository.upsert(feed.id, valid_for)
    return feeds


@pytest.mark.asyncio
async def test_eligible_feeds(scheduled_feeds, feed_repository):
    eligible = await feed_repository.get_eligible({ParserId.WEB, ParserId.RANOBE_ME})

    assert eligible == [
        scheduled_feeds["missing"],
        scheduled_feeds["due"],
        scheduled_feeds["naive-due"],
    ]


@pytest.mark.asyncio
async def test_eligible_feeds_without_supported_parsers(
    scheduled_feeds, feed_repository
):
    assert await feed_repository.get_eligible(set()) == []


@pytest.mark.asyncio
async def test_dispatch_only_eligible_feeds(
    scheduled_feeds, feed_repository, feed_parser_repository, items_repository
):
    submitted = []

    async def enqueue(request):
        payload = await request.json()
        feed = Feed.model_validate_json(payload["data"][0])
        assert payload["function"] == f"gkfeed.process_feed_{feed.type}"
        submitted.append(feed)
        return web.json_response({"task_id": str(feed.id)})

    async def result(request):
        return web.json_response(
            {"status": "completed", "result": FeedResult(items=[]).model_dump_json()}
        )

    app = web.Application()
    app.router.add_post("/enqueue", enqueue)
    app.router.add_get("/result/{task_id}", result)
    async with TestServer(app) as server:
        dispatcher = Dispatcher(
            broker=BrokerService(str(server.make_url("/"))),
            feed_repository=feed_repository,
            feed_parser_repository=feed_parser_repository,
            items_repository=items_repository,
            parsers={ParserId.WEB: BaseFeed, ParserId.RANOBE_ME: BaseFeed},
        )
        await dispatcher.dispatch()
        assert submitted == [
            scheduled_feeds["missing"],
            scheduled_feeds["due"],
            scheduled_feeds["naive-due"],
        ]

        for feed in submitted:
            schedule = await feed_parser_repository.get_by_feed_id(feed.id)
            assert schedule is not None
            assert schedule.valid_for.replace(tzinfo=UTC) > datetime.now(UTC)

        await dispatcher.dispatch()
        assert len(submitted) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("parser_id", list(ParserId))
async def test_parser_id_round_trip(feed_repository, session_factory, parser_id):
    payload = {
        "id": 0,
        "title": "Parser ID round trip",
        "url": "https://example.com/feed",
        "type": parser_id.value,
    }
    feed = Feed.model_validate_json(json.dumps(payload))
    created = await feed_repository.create(feed)
    found = await feed_repository.get_by_id(created.id)

    assert found.type is parser_id
    assert found.model_dump(mode="json")["type"] == parser_id.value
    assert Feed.model_validate_json(found.model_dump_json()) == found
    assert await feed_repository.get_all() == [found]
    assert await feed_repository.get_eligible({parser_id.value}) == [found]
    async with session_factory() as session:
        stored_type = await session.scalar(
            select(FeedModel.type).where(FeedModel.id == found.id)
        )
    assert stored_type == parser_id.value


@pytest.mark.asyncio
@pytest.mark.parametrize("parser_type", ["test", "unknown", "unsupported", "second"])
async def test_invalid_parser_payload_is_not_persisted(feed_repository, parser_type):
    payload = json.dumps({
        "id": 0,
        "title": "Invalid parser",
        "url": "https://example.com/invalid",
        "type": parser_type,
    })
    with pytest.raises(ValidationError, match="type"):
        await feed_repository.create(Feed.model_validate_json(payload))
    assert await feed_repository.get_all() == []


@pytest.mark.asyncio
async def test_unknown_stored_parser_is_rejected(feed_repository, session_factory):
    # Simulate legacy data written before parser identifiers were validated.
    async with session_factory() as session, session.begin():
        stored = FeedModel(
            title="Legacy feed", url="https://example.com/legacy", type="unknown"
        )
        session.add(stored)
        await session.flush()
        feed_id = stored.id

    with pytest.raises(ValueError, match="unknown"):
        await feed_repository.get_by_id(feed_id)
    with pytest.raises(ValueError, match="unknown"):
        await feed_repository.get_all()
    with pytest.raises(ValueError, match="unknown"):
        await feed_repository.get_eligible({"unknown"})
