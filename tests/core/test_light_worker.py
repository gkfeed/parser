import asyncio
import json
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from app.core.light_worker import run_light_workers
from app.core.parser_id import ParserId
from app.serializers.feed import Feed, FeedFailure, FeedResult
from app.services.broker import BrokerError, BrokerService


class WorkerBoundary:
    """Local broker and feed sources with independently controlled I/O."""

    def __init__(self) -> None:
        self.queues: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
        self.polls: list[str] = []
        self.claimed: list[str] = []
        self.active: set[str] = set()
        self.peak_active = 0
        self.results: dict[str, str] = {}
        self.errors: dict[str, str] = {}
        self.claim_started: dict[str, asyncio.Event] = defaultdict(asyncio.Event)
        self.feed_started: dict[str, asyncio.Event] = defaultdict(asyncio.Event)
        self.submission_started: dict[str, asyncio.Event] = defaultdict(asyncio.Event)
        self.completed: dict[str, asyncio.Event] = defaultdict(asyncio.Event)
        self.claim_gates: dict[str, asyncio.Event] = {}
        self.feed_gates: dict[str, asyncio.Event] = {}
        self.submission_gates: dict[str, asyncio.Event] = {}
        self.reject_submissions = False
        app = web.Application()
        app.router.add_post("/enqueue", self.enqueue_request)
        app.router.add_get("/get_task", self.claim_request)
        app.router.add_post("/submit_result", self.submit_result)
        app.router.add_post("/submit_error", self.submit_error)
        app.router.add_get("/feed/{id}", self.feed_request)
        self.server = TestServer(app)

    @property
    def broker(self) -> BrokerService:
        return BrokerService(str(self.server.make_url("/")))

    async def enqueue(self, task_id: int, parser: ParserId = ParserId.WEB) -> None:
        feed = Feed(
            id=task_id,
            title=f"Feed {task_id}",
            type=parser,
            url=str(self.server.make_url(f"/feed/{task_id}?format={parser}")),
        )
        await self.broker.enqueue(parser.task_name, [feed.model_dump_json()])

    async def enqueue_request(self, request: web.Request) -> web.Response:
        payload = await request.json()
        task_id = str(json.loads(payload["data"][0])["id"])
        self.queues[payload["function"]].append({"task_id": task_id, **payload})
        return web.json_response({"task_id": task_id})

    async def claim_request(self, request: web.Request) -> web.Response:
        function = request.query["function"]
        self.polls.append(function)
        if not self.queues[function]:
            return web.json_response({})
        task = self.queues[function].popleft()
        task_id = task["task_id"]
        self.claimed.append(task_id)
        self.active.add(task_id)
        self.peak_active = max(self.peak_active, len(self.active))
        self.claim_started[task_id].set()
        await self.wait_gate(self.claim_gates, task_id)
        return web.json_response(task)

    async def feed_request(self, request: web.Request) -> web.Response:
        task_id = request.match_info["id"]
        self.feed_started[task_id].set()
        await self.wait_gate(self.feed_gates, task_id)
        if request.query["format"] == "shiki":
            return web.Response(
                text='<h1>Show</h1><div class="b-menu-links">'
                '<div class="entry"><span><time datetime="2026-01-01T00:00:00Z">'
                "Today</time></span><span>Episode 1</span></div></div>",
                content_type="text/html",
            )
        if request.query["format"] == "invalid":
            return web.Response(status=503)
        return web.Response(
            text="<rss><channel><item><title>Entry</title>"
            "<description>Text</description><link>https://example.test/item</link>"
            f"<guid>{task_id}</guid><pubDate>Thu, 01 Jan 2026 00:00:00 GMT</pubDate>"
            "</item></channel></rss>",
            content_type="application/rss+xml",
        )

    async def submit_result(self, request: web.Request) -> web.Response:
        return await self.submit(request, self.results, "result")

    async def submit_error(self, request: web.Request) -> web.Response:
        return await self.submit(request, self.errors, "error_message")

    async def submit(
        self, request: web.Request, destination: dict[str, str], field: str
    ) -> web.Response:
        payload = await request.json()
        task_id = payload["task_id"]
        self.submission_started[task_id].set()
        await self.wait_gate(self.submission_gates, task_id)
        if self.reject_submissions:
            return web.json_response({"error": "unavailable"}, status=503)
        destination[task_id] = payload[field]
        self.active.remove(task_id)
        self.completed[task_id].set()
        return web.json_response({})

    @staticmethod
    async def wait_gate(gates: dict[str, asyncio.Event], task_id: str) -> None:
        if task_id in gates:
            await gates[task_id].wait()

    def release(self) -> None:
        gates = (*self.claim_gates.values(), *self.feed_gates.values())
        for gate in (*gates, *self.submission_gates.values()):
            gate.set()


@pytest.fixture
async def boundary() -> AsyncIterator[WorkerBoundary]:
    boundary = WorkerBoundary()
    await boundary.server.start_server()
    try:
        yield boundary
    finally:
        boundary.release()
        await boundary.server.close()


async def stop_worker(worker: asyncio.Task[None], boundary: WorkerBoundary) -> None:
    if not worker.cancelling():
        worker.cancel()
    boundary.release()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(worker, 5)


async def test_fast_feed_finishes_while_slow_feed_waits(
    boundary: WorkerBoundary,
) -> None:
    boundary.feed_gates["1"] = asyncio.Event()
    for task_id in (1, 2, 3):
        await boundary.enqueue(task_id)
    await boundary.enqueue(4, ParserId.SHIKI)
    worker = asyncio.create_task(
        run_light_workers(
            [ParserId.WEB, ParserId.SHIKI], concurrency=2, broker=boundary.broker
        )
    )
    try:
        await asyncio.wait_for(boundary.completed["4"].wait(), 5)
        await asyncio.wait_for(boundary.completed["3"].wait(), 5)
        assert boundary.feed_started["1"].is_set()
        assert not boundary.completed["1"].is_set()
        assert boundary.claimed[:2] == ["1", "4"]
        assert boundary.peak_active == 2
        assert len(FeedResult.model_validate_json(boundary.results["4"]).items) == 1
        assert not boundary.errors
    finally:
        await stop_worker(worker, boundary)
    assert len(boundary.results) == 4
    assert not boundary.active


async def test_slots_include_pending_broker_submissions(
    boundary: WorkerBoundary,
) -> None:
    for task_id in (1, 2, 3, 4):
        boundary.submission_gates[str(task_id)] = asyncio.Event()
        await boundary.enqueue(task_id)
    worker = asyncio.create_task(
        run_light_workers([ParserId.WEB], concurrency=2, broker=boundary.broker)
    )
    try:
        await asyncio.wait_for(boundary.submission_started["1"].wait(), 5)
        await asyncio.wait_for(boundary.submission_started["2"].wait(), 5)
        await asyncio.sleep(0.05)
        assert boundary.claimed == ["1", "2"]
        boundary.submission_gates["1"].set()
        await asyncio.wait_for(boundary.submission_started["3"].wait(), 5)
        worker.cancel()
        await asyncio.sleep(0)
        assert not worker.done()
        assert boundary.claimed == ["1", "2", "3"]
    finally:
        await stop_worker(worker, boundary)
    assert set(boundary.results) == {"1", "2", "3"}
    assert boundary.peak_active == 2
    assert not boundary.active


async def test_shutdown_finishes_claim_feed_and_submission(
    boundary: WorkerBoundary,
) -> None:
    boundary.claim_gates["1"] = asyncio.Event()
    boundary.feed_gates["1"] = asyncio.Event()
    boundary.submission_gates["1"] = asyncio.Event()
    await boundary.enqueue(1)
    await boundary.enqueue(2)
    worker = asyncio.create_task(
        run_light_workers([ParserId.WEB], concurrency=2, broker=boundary.broker)
    )
    try:
        await asyncio.wait_for(boundary.claim_started["1"].wait(), 5)
        worker.cancel()
        await asyncio.sleep(0)
        assert not worker.done()
        boundary.claim_gates["1"].set()
        await asyncio.wait_for(boundary.feed_started["1"].wait(), 5)
        assert not worker.done()
        boundary.feed_gates["1"].set()
        await asyncio.wait_for(boundary.submission_started["1"].wait(), 5)
        assert not worker.done()
        assert boundary.claimed == ["1"]
    finally:
        await stop_worker(worker, boundary)
    assert set(boundary.results) == {"1"}
    assert not boundary.active


@pytest.mark.parametrize("slow_feed", [False, True])
async def test_empty_queues_use_bounded_fair_idle_polling(
    boundary: WorkerBoundary,
    slow_feed: bool,
) -> None:
    if slow_feed:
        boundary.feed_gates["1"] = asyncio.Event()
        await boundary.enqueue(1)
    worker = asyncio.create_task(
        run_light_workers(
            [ParserId.WEB, ParserId.SHIKI],
            concurrency=2,
            idle_poll_min=0.03,
            idle_poll_max=0.12,
            broker=boundary.broker,
        )
    )
    try:
        await asyncio.sleep(0.4)
        assert 6 <= len(boundary.polls) <= 14
        assert boundary.polls[::2] == ["gkfeed.process_feed_web"] * len(
            boundary.polls[::2]
        )
        assert boundary.polls[1::2] == ["gkfeed.process_feed_shiki"] * len(
            boundary.polls[1::2]
        )
    finally:
        await stop_worker(worker, boundary)


async def test_broker_submission_failures_escape_worker(
    boundary: WorkerBoundary,
) -> None:
    boundary.reject_submissions = True
    await boundary.enqueue(1)
    with pytest.raises(BrokerError, match="Failed to submit error"):
        await asyncio.wait_for(
            run_light_workers([ParserId.WEB], concurrency=1, broker=boundary.broker), 5
        )
    assert not boundary.results
    assert not boundary.errors


@pytest.mark.parametrize("payload_parser", ["unknown", "shiki"])
async def test_light_worker_rejects_invalid_or_misrouted_payload(
    boundary: WorkerBoundary, payload_parser: str
) -> None:
    payload = {
        "id": 1,
        "title": "Invalid feed",
        "url": str(boundary.server.make_url("/feed/1")),
        "type": payload_parser,
    }
    await boundary.broker.enqueue(ParserId.WEB.task_name, [json.dumps(payload)])
    with pytest.raises(ValueError, match="Invalid feed for parser web"):
        await asyncio.wait_for(
            run_light_workers([ParserId.WEB], concurrency=1, broker=boundary.broker), 5
        )
    assert boundary.errors == {"1": "invalid_feed"}
    assert not boundary.feed_started
    assert not boundary.results


async def test_failed_feed_submits_failure_and_next_feed_runs(
    boundary: WorkerBoundary,
) -> None:
    feed = Feed(
        id=1,
        title="Unavailable",
        type=ParserId.WEB,
        url=str(boundary.server.make_url("/feed/1?format=invalid")),
    )
    await boundary.broker.enqueue("gkfeed.process_feed_web", [feed.model_dump_json()])
    await boundary.enqueue(2)
    worker = asyncio.create_task(
        run_light_workers([ParserId.WEB], concurrency=1, broker=boundary.broker)
    )
    try:
        await asyncio.wait_for(boundary.completed["2"].wait(), 5)
        failure = FeedFailure.model_validate_json(boundary.errors["1"])
        assert failure.reason == "http_status_503"
        assert set(boundary.results) == {"2"}
    finally:
        await stop_worker(worker, boundary)
