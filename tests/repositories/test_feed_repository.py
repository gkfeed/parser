from datetime import UTC, datetime, timedelta

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from app.core.dispatcher import Dispatcher
from app.extensions.parsers.base import BaseFeed
from app.serializers.feed import Feed
from app.services.broker import BrokerService
from app.services.repositories.feed import FeedRepository
from app.services.repositories.feed_parser import FeedParserRepository


@pytest.mark.asyncio
async def test_feed_repository():
    feed_data = Feed(
        id=0,
        title="Test Feed",
        url=f"https://test.com/{datetime.now(UTC).timestamp()}",
        type="test",
    )

    # Test Create
    created_feed = await FeedRepository.create(feed_data)
    assert created_feed.id != 0
    assert created_feed.title == "Test Feed"

    # Test Get All
    all_feeds = await FeedRepository.get_all()
    assert any(f.id == created_feed.id for f in all_feeds)

    # Test Get By ID
    found_feed = await FeedRepository.get_by_id(created_feed.id)
    assert found_feed.title == "Test Feed"

    # Clean up
    await FeedRepository.delete_by_id(created_feed.id)


@pytest.fixture
async def scheduled_feeds():
    now = datetime.now(UTC)
    cases = [
        ("future", "test", now + timedelta(days=1)),
        ("missing", "test", None),
        ("unsupported-missing", "unsupported", None),
        ("due", "test", now - timedelta(days=1)),
        ("unsupported-due", "unsupported", now - timedelta(days=1)),
        ("naive-due", "second", now.replace(tzinfo=None) - timedelta(days=1)),
    ]
    feeds = {}
    for title, parser_type, valid_for in cases:
        feed = await FeedRepository.create(
            Feed(id=0, title=title, url=f"https://example.com/{title}", type=parser_type)
        )
        feeds[title] = feed
        if valid_for is not None:
            await FeedParserRepository.upsert(feed.id, valid_for)
    return feeds


@pytest.mark.asyncio
async def test_eligible_feeds(scheduled_feeds):
    eligible = await FeedRepository.get_eligible({"test", "second"})

    assert eligible == [
        scheduled_feeds["missing"],
        scheduled_feeds["due"],
        scheduled_feeds["naive-due"],
    ]


@pytest.mark.asyncio
async def test_eligible_feeds_without_supported_parsers(scheduled_feeds):
    assert await FeedRepository.get_eligible(set()) == []


@pytest.mark.asyncio
async def test_dispatch_only_eligible_feeds(scheduled_feeds):
    submitted = []

    async def enqueue(request):
        payload = await request.json()
        feed = Feed.model_validate_json(payload["data"][0])
        assert payload["function"] == f"gkfeed.process_feed_{feed.type}"
        submitted.append(feed)
        return web.json_response({"task_id": str(feed.id)})

    async def result(request):
        return web.json_response({"status": "completed", "result": "[]"})

    app = web.Application()
    app.router.add_post("/enqueue", enqueue)
    app.router.add_get("/result/{task_id}", result)
    async with TestServer(app) as server:
        dispatcher = Dispatcher(
            broker=BrokerService(str(server.make_url("/"))),
            parsers={"test": BaseFeed, "second": BaseFeed},
        )
        await dispatcher.dispatch()
        assert submitted == [
            scheduled_feeds["missing"],
            scheduled_feeds["due"],
            scheduled_feeds["naive-due"],
        ]

        for feed in submitted:
            schedule = await FeedParserRepository.get_by_feed_id(feed.id)
            assert schedule is not None
            assert schedule.valid_for.replace(tzinfo=UTC) > datetime.now(UTC)

        await dispatcher.dispatch()
        assert len(submitted) == 3
