import asyncio
import json
from typing import cast

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import StatementError

from app.core.dispatcher import Dispatcher
from app.core.parser_id import ParserId
from app.core.worker import run_worker
from app.models.feed import Feed as StoredFeed
from app.parsers import PARSERS
from app.serializers.feed import Feed, FeedResult
from app.services.broker import BrokerService
from app.services.container import Container
from app.services.repositories.feed import FeedRepository
from app.services.repositories.feed_parser import FeedParserRepository

# Existing DB values and broker suffixes are an external compatibility contract.
PERSISTED_IDS = (
    "web",
    "tiktok",
    "kinogo",
    "twitch",
    "yummyanime",
    "shiki",
    "reddit",
    "vk",
    "vkvideo",
    "yt",
    "ranobe.me",
    "spoti",
    "rezka",
    "inst",
    "stories",
    "insolarance",
    "mangalib",
    "x",
    "spoti:playlist",
    "onefootball",
    "rtl",
    "rezka:collection",
    "matreshka",
    "shiki:ongoing",
    "anilibria",
    "pornhub",
    "hltv",
    "liquidpedia",
    "sasflix",
    "porno365",
    "author.today",
)


@pytest.mark.parametrize("persisted_id", PERSISTED_IDS)
async def test_existing_parser_ids_round_trip_through_db_and_json(persisted_id):
    async with Container.get_data().db_session() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO feed (id, title, url, type) VALUES (1, :title, :url, :type)"
            ),
            {"title": "Feed", "url": "https://example.com/feed", "type": persisted_id},
        )

    feed = await FeedRepository.get_by_id(1)
    assert isinstance(feed.type, ParserId)
    assert feed.type in PARSERS
    assert feed.type.task_name == f"gkfeed.process_feed_{persisted_id}"
    assert json.loads(feed.model_dump_json())["type"] == persisted_id
    assert Feed.model_validate_json(feed.model_dump_json()) == feed
    assert await FeedRepository.get_eligible({feed.type}) == [feed]

    copied = await FeedRepository.create(feed)
    async with Container.get_data().db_session() as session:
        stored = await session.scalar(
            text("SELECT type FROM feed WHERE id = :id"), {"id": copied.id}
        )
    assert stored == persisted_id
    assert await FeedRepository.get_by_id(copied.id) == copied


@pytest.mark.parametrize(
    "unsupported", ["test", "unknown", "ranobeme", "WEB", "", None, 1]
)
async def test_json_rejects_unsupported_parser_ids(unsupported):
    payload = {
        "id": 1,
        "title": "Feed",
        "url": "https://example.com",
        "type": unsupported,
    }
    with pytest.raises(ValidationError, match="type"):
        Feed.model_validate_json(json.dumps(payload))
    assert await FeedRepository.get_all() == []


async def test_existing_invalid_db_value_is_rejected_on_read():
    async with Container.get_data().db_session() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO feed (id, title, url, type) VALUES (1, 'Feed', '', 'unknown')"
            )
        )

    with pytest.raises(LookupError, match="unknown"):
        await FeedRepository.get_by_id(1)


async def test_orm_rejects_unsupported_id_before_persistence():
    with pytest.raises(StatementError, match="unknown"):
        async with Container.get_data().db_session() as session, session.begin():
            session.add(StoredFeed(id=1, title="Feed", url="", type="unknown"))
            await session.flush()
    assert await FeedRepository.get_all() == []


async def test_feed_rejects_invalid_parser_assignment():
    feed = Feed(id=1, title="Feed", url="", type=ParserId.WEB)
    with pytest.raises(ValidationError, match="type"):
        feed.type = cast(ParserId, "unknown")
    assert feed.type is ParserId.WEB


async def test_worker_rejects_invalid_id_before_contacting_broker():
    with pytest.raises(ValueError, match="unknown"):
        await run_worker(cast(ParserId, "unknown"))


@pytest.fixture
async def broker_boundary(monkeypatch):
    tasks = []
    results = []
    errors = []
    feed_requests = []

    async def enqueue(request):
        tasks.append(await request.json())
        return web.json_response({"task_id": "task-1"})

    async def get_task(request):
        assert request.query["function"] == "gkfeed.process_feed_web"
        return web.json_response({"task_id": "task-1", **tasks[0]})

    async def submit_result(request):
        results.append(await request.json())
        return web.json_response({})

    async def submit_error(request):
        errors.append(await request.json())
        return web.json_response({})

    async def get_result(request):
        if not results:
            return web.json_response({"status": "pending"})
        return web.json_response(
            {"status": "completed", "result": results[0]["result"]}
        )

    async def rss(request):
        feed_requests.append(request.path)
        return web.Response(
            text="""<rss version="2.0"><channel><title>Feed</title><item>
            <title>Post</title><link>https://example.com/post</link>
            <description>Body</description><pubDate>22 Oct 2026 12:00:00 GMT</pubDate>
            <guid>post-1</guid></item></channel></rss>""",
            content_type="application/rss+xml",
        )

    app = web.Application()
    app.router.add_post("/enqueue", enqueue)
    app.router.add_get("/get_task", get_task)
    app.router.add_post("/submit_result", submit_result)
    app.router.add_post("/submit_error", submit_error)
    app.router.add_get("/result/{task_id}", get_result)
    app.router.add_get("/feed", rss)
    async with TestServer(app) as server:
        url = str(server.make_url("/"))
        monkeypatch.setattr("app.core.worker.BROKER_URL", url)
        yield url, tasks, results, errors, feed_requests


async def test_db_dispatch_worker_and_broker_keep_existing_wire_values(broker_boundary):
    url, tasks, results, errors, feed_requests = broker_boundary
    feed = await FeedRepository.create(
        Feed(id=0, title="Feed", url=url + "feed", type=ParserId.WEB)
    )
    dispatcher = Dispatcher(broker=BrokerService(url))

    await asyncio.wait_for(
        asyncio.gather(dispatcher.dispatch(), run_worker(parser_id=ParserId.WEB)),
        timeout=10,
    )

    assert len(tasks) == 1
    assert tasks[0]["function"] == "gkfeed.process_feed_web"
    assert json.loads(tasks[0]["data"][0])["type"] == "web"
    assert len(results) == 1
    result = FeedResult.model_validate_json(results[0]["result"])
    assert result.items[0].title == "Post"
    assert result.items[0].hash is not None
    assert errors == []
    assert feed_requests == ["/feed"]
    assert await FeedParserRepository.get_by_feed_id(feed.id) is not None


@pytest.mark.parametrize("parser_id", ["unknown", "spoti:playlist"])
async def test_worker_rejects_invalid_or_misrouted_payload(broker_boundary, parser_id):
    url, tasks, results, errors, feed_requests = broker_boundary
    payload = {"id": 1, "title": "Feed", "url": url + "feed", "type": parser_id}
    tasks.append({"function": "gkfeed.process_feed_web", "data": [json.dumps(payload)]})

    with pytest.raises(ValueError, match="Invalid feed for parser web"):
        await run_worker(ParserId.WEB)

    assert results == []
    assert errors == [{"task_id": "task-1", "error_message": "invalid_feed"}]
    assert feed_requests == []
