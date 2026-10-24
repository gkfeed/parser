import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from app.serializers.feed import FeedFailure
from app.services.broker import (
    BrokerError,
    BrokerFeedUnavailable,
    BrokerNoWorker,
    BrokerService,
)
from app.services.http import HttpService


@dataclass
class BrokerBoundary:
    jobs: dict = field(default_factory=dict)
    polls: dict = field(default_factory=lambda: defaultdict(list))
    transports: set = field(default_factory=set)
    cancelled: list = field(default_factory=list)
    observed: asyncio.Event = field(default_factory=asyncio.Event)
    initial_status: str = "pending"
    delay_after_first_poll: float = 0
    url: str = ""

    async def enqueue(self, request):
        payload = await request.json()
        task_id = str(len(self.jobs) + 1)
        self.jobs[task_id] = {"status": self.initial_status, "result": None, **payload}
        self.transports.add(request.transport)
        return web.json_response({"task_id": task_id})

    async def result(self, request):
        task_id = request.match_info["task_id"]
        self.transports.add(request.transport)
        self.polls[task_id].append(asyncio.get_running_loop().time())
        self.observed.set()
        if len(self.polls[task_id]) > 1:
            await asyncio.sleep(self.delay_after_first_poll)
        return web.json_response(self.jobs[task_id])

    async def claim(self, request):
        for task_id, job in self.jobs.items():
            if job["status"] != "pending":
                continue
            job["status"] = "processing"
            return web.json_response({"task_id": task_id, **job})
        return web.json_response({"task_id": None})

    async def submit(self, request):
        payload = await request.json()
        failed = "error_message" in payload
        self.jobs[payload["task_id"]].update(
            status="failed" if failed else "completed",
            result=payload.get("error_message") if failed else payload["result"],
        )
        return web.json_response({"ok": True})

    async def cancel(self, request):
        task_id = request.match_info["task_id"]
        self.cancelled.append(task_id)
        return web.json_response(
            {
                "error": "Task already acknowledged",
                "task_id": task_id,
                "status": self.jobs[task_id]["status"],
            }
        )


@pytest.fixture
async def broker_boundary():
    boundary = BrokerBoundary()
    app = web.Application()
    app.router.add_post("/enqueue", boundary.enqueue)
    app.router.add_get("/result/{task_id}", boundary.result)
    app.router.add_get("/get_task", boundary.claim)
    app.router.add_post("/submit_result", boundary.submit)
    app.router.add_post("/submit_error", boundary.submit)
    app.router.add_delete("/cancel/{task_id}", boundary.cancel)
    async with TestServer(app) as server:
        boundary.url = str(server.make_url("/"))
        yield boundary


def new_broker(boundary):
    return BrokerService(
        boundary.url, poll_initial_interval=0.01, poll_max_interval=0.04
    )


async def finish_jobs(broker, count):
    tasks = []
    deadline = asyncio.get_running_loop().time() + 1
    while len(tasks) < count:
        assert asyncio.get_running_loop().time() < deadline
        task = await broker.get_task("test")
        if task is None:
            await asyncio.sleep(0.001)
            continue
        tasks.append(task)
    await asyncio.sleep(0.1)
    retry_at = datetime(2030, 1, 1, tzinfo=UTC)
    await broker.submit_result(tasks[0].id, "success")
    await broker.submit_error(tasks[1].id, "failed")
    await broker.submit_error(
        tasks[2].id,
        FeedFailure(
            error_type="feed_unavailable", reason="refused", retry_at=retry_at
        ).model_dump_json(),
    )
    return asyncio.get_running_loop().time(), retry_at


async def test_multiple_jobs_back_off_and_preserve_results_and_failures(
    broker_boundary,
):
    broker = new_broker(broker_boundary)
    async with HttpService(connection_limit=2, per_host_limit=2):
        waiting = [
            asyncio.create_task(broker.put_and_wait_for_result("test", [i], 2))
            for i in range(3)
        ]
        await asyncio.wait_for(broker_boundary.observed.wait(), 1)
        completed_at, retry_at = await finish_jobs(broker, 3)
        outcomes = await asyncio.gather(*waiting, return_exceptions=True)
        detected_at = asyncio.get_running_loop().time()
    assert outcomes[0] == "success"
    assert isinstance(outcomes[1], BrokerError)
    assert isinstance(outcomes[2], BrokerFeedUnavailable)
    assert outcomes[2].reason == "refused"
    assert outcomes[2].retry_at == retry_at
    assert detected_at - completed_at < 0.15
    assert sum(map(len, broker_boundary.polls.values())) < 30
    assert len(broker_boundary.transports) <= 2
    assert broker_boundary.cancelled == []


async def test_pending_deadline_retains_job_for_retry(broker_boundary):
    broker = new_broker(broker_boundary)
    async with HttpService():
        with pytest.raises(BrokerNoWorker) as error:
            await broker.put_and_wait_for_result("test", [], 0.06, task_key="feed")
        task_id = error.value.task_id
        assert broker_boundary.cancelled == []
        await broker.submit_result(task_id, "later")
        assert (
            await broker.put_and_wait_for_result("test", [], 1, task_key="feed")
            == "later"
        )
        assert len(broker_boundary.jobs) == 1
        with pytest.raises(BrokerNoWorker):
            await broker.put_and_wait_for_result("test", [], 0.02, task_key="feed")
    assert len(broker_boundary.jobs) == 2


async def test_processing_deadline_requests_cancellation_and_clears_key(
    broker_boundary,
):
    broker_boundary.initial_status = "processing"
    broker = new_broker(broker_boundary)
    started = asyncio.get_running_loop().time()
    async with HttpService():
        with pytest.raises(BrokerError, match="Timeout waiting"):
            await broker.put_and_wait_for_result("test", [], 0.06, task_key="feed")
        assert asyncio.get_running_loop().time() - started < 0.3
        assert broker_boundary.cancelled == ["1"]
        with pytest.raises(BrokerError, match="Timeout waiting"):
            await broker.put_and_wait_for_result("test", [], 0.02, task_key="feed")
    assert len(broker_boundary.jobs) == 2
    assert broker_boundary.cancelled == ["1", "2"]


async def test_slow_result_request_cannot_extend_job_deadline(broker_boundary):
    broker_boundary.initial_status = "processing"
    broker_boundary.delay_after_first_poll = 0.25
    broker = new_broker(broker_boundary)
    started = asyncio.get_running_loop().time()
    async with HttpService():
        with pytest.raises(BrokerError, match="Timeout waiting"):
            await broker.put_and_wait_for_result("test", [], 0.05)
    assert asyncio.get_running_loop().time() - started < 0.2
    assert broker_boundary.cancelled == ["1"]


async def test_cancelling_waiter_stops_polling_and_retains_remote_job(broker_boundary):
    broker = new_broker(broker_boundary)
    async with HttpService():
        waiting = asyncio.create_task(
            broker.put_and_wait_for_result("test", [], 2, task_key="feed")
        )
        await asyncio.wait_for(broker_boundary.observed.wait(), 1)
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        count = len(broker_boundary.polls["1"])
        await asyncio.sleep(0.06)
        assert len(broker_boundary.polls["1"]) == count
        assert broker_boundary.cancelled == []
        await broker.submit_result("1", "resumed")
        assert (
            await broker.put_and_wait_for_result("test", [], 1, task_key="feed")
            == "resumed"
        )
    assert len(broker_boundary.jobs) == 1


async def test_malformed_status_raises_instead_of_waiting_until_timeout(
    broker_boundary,
):
    broker_boundary.initial_status = ""
    async with HttpService():
        with pytest.raises(BrokerError, match="Missing task status"):
            await new_broker(broker_boundary).put_and_wait_for_result("test", [], 2)
    assert len(broker_boundary.polls["1"]) == 1


async def test_failed_job_clears_retry_key(broker_boundary):
    broker_boundary.initial_status = "failed"
    broker = new_broker(broker_boundary)
    async with HttpService():
        with pytest.raises(BrokerError, match="Task failed"):
            await broker.put_and_wait_for_result("test", [], 1, task_key="feed")
        with pytest.raises(BrokerError, match="Task failed"):
            await broker.put_and_wait_for_result("test", [], 1, task_key="feed")
    assert len(broker_boundary.jobs) == 2
