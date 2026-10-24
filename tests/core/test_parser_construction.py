from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from socket import socket
from typing import Any

import pytest
from aiohttp import web

from app.core.parsers import create_parser
from app.core.worker import run_worker
from app.parsers import PARSERS, Parser
from app.parsers.web import WebFeed
from app.serializers.feed import Feed, FeedResult, Item

pytestmark = pytest.mark.integration

RSS_ITEM = """<item>
<title>Local article</title><description>Article body</description>
<link>https://example.test/article</link><guid>local-article</guid>
<pubDate>Thu, 22 Oct 2026 09:00:00 GMT</pubDate>
</item>"""


@dataclass
class LocalBoundary:
    url: str
    feed: Feed
    results: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


@pytest.fixture
async def parser_boundary() -> AsyncIterator[LocalBoundary]:
    listener = socket()
    listener.bind(("127.0.0.1", 0))
    url = f"http://127.0.0.1:{listener.getsockname()[1]}"
    boundary = LocalBoundary(
        url, Feed(id=1, title="Local feed", type="web", url=f"{url}/rss")
    )

    async def get_task(request: web.Request) -> web.Response:
        assert request.query["function"] == f"gkfeed.process_feed_{boundary.feed.type}"
        return web.json_response(
            {"task_id": "local-task", "data": [boundary.feed.model_dump_json()]}
        )

    async def rss(request: web.Request) -> web.Response:
        item = "" if "empty" in request.query else RSS_ITEM
        return web.Response(
            text=f"<rss version='2.0'><channel>{item}</channel></rss>",
            content_type="application/rss+xml",
        )

    async def submit_result(request: web.Request) -> web.Response:
        boundary.results.append(await request.json())
        return web.json_response({})

    async def submit_error(request: web.Request) -> web.Response:
        boundary.errors.append(await request.json())
        return web.json_response({})

    application = web.Application()
    application.router.add_get("/get_task", get_task)
    application.router.add_get("/rss", rss)
    application.router.add_post("/submit_result", submit_result)
    application.router.add_post("/submit_error", submit_error)
    runner = web.AppRunner(application)
    await runner.setup()
    try:
        await web.SockSite(runner, listener).start()
        yield boundary
    finally:
        await runner.cleanup()
        listener.close()


@pytest.mark.parametrize("empty", [False, True])
async def test_worker_constructs_registered_parser_and_submits_hashed_rss(
    parser_boundary: LocalBoundary, monkeypatch: pytest.MonkeyPatch, empty: bool
) -> None:
    if empty:
        parser_boundary.feed.url += "?empty"
    monkeypatch.setattr("app.core.worker.BROKER_URL", parser_boundary.url)

    await run_worker("web")

    assert parser_boundary.errors == []
    assert len(parser_boundary.results) == 1
    submitted = parser_boundary.results[0]
    assert submitted["task_id"] == "local-task"
    result = FeedResult.model_validate_json(submitted["result"])
    assert result.retry_at is None
    if empty:
        assert result.items == []
        return
    assert len(result.items) == 1
    assert result.items[0].title == "Local article"
    assert result.items[0].hash == sha256(b"local-article").hexdigest()


async def test_worker_preserves_typed_parser_retry(
    parser_boundary: LocalBoundary, monkeypatch: pytest.MonkeyPatch
) -> None:
    retry_at = datetime.now(UTC) + timedelta(hours=3)

    class RetryFeed(WebFeed):
        async def _parse_items(self) -> list[Item]:
            items = await super()._parse_items()
            self.retry_at = retry_at
            return items

    parser_boundary.feed.type = "fixture:retry"
    monkeypatch.setitem(PARSERS, parser_boundary.feed.type, RetryFeed)
    monkeypatch.setattr("app.core.worker.BROKER_URL", parser_boundary.url)

    await run_worker(parser_boundary.feed.type)

    assert parser_boundary.errors == []
    assert len(parser_boundary.results) == 1
    result = FeedResult.model_validate_json(parser_boundary.results[0]["result"])
    assert result.retry_at == retry_at
    assert len(result.items) == 1
    assert result.items[0].hash == sha256(b"local-article").hexdigest()


async def test_worker_reports_unknown_parser_to_broker(
    parser_boundary: LocalBoundary, monkeypatch: pytest.MonkeyPatch
) -> None:
    parser_boundary.feed.type = "unknown"
    monkeypatch.setattr("app.core.worker.BROKER_URL", parser_boundary.url)

    await run_worker(parser_boundary.feed.type)

    assert parser_boundary.results == []
    assert parser_boundary.errors == [
        {"task_id": "local-task", "error_message": "failed"}
    ]


@pytest.mark.parametrize("parser", list(Parser))
async def test_registered_parsers_accept_feed_only_and_legacy_empty_data(
    parser: Parser,
) -> None:
    feed = Feed(
        id=1, title="Construction", type=parser.value.id, url="https://example.test"
    )
    instance = create_parser(feed)
    assert instance.feed == feed
    assert instance.retry_at is None

    legacy_data: dict[str, object] = {}
    legacy_instance = parser.value.handler(feed, legacy_data)
    assert legacy_instance.feed == feed
    assert legacy_data == {}
    with pytest.raises(ValueError, match="Parser data is no longer supported"):
        parser.value.handler(feed, {"retry_at": datetime.now(UTC)})


async def test_unknown_parser_fails_before_fetching() -> None:
    feed = Feed(id=1, title="Unknown", type="unknown", url="https://example.test")
    with pytest.raises(ValueError, match="No parser found for feed type: unknown"):
        create_parser(feed)
