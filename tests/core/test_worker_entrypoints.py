import asyncio
import json
import os
import signal
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from aiohttp import web

from app.configs.workers import heavy_parsers, light_parsers


@dataclass
class WorkerBoundary:
    url: str = ""
    polls: list[str] = field(default_factory=list)
    tasks: dict[str, list[dict]] = field(default_factory=dict)
    results: list[dict] = field(default_factory=list)
    broker_unavailable: bool = False
    feed_started: asyncio.Event = field(default_factory=asyncio.Event)
    release_feed: asyncio.Event = field(default_factory=asyncio.Event)
    result_submitted: asyncio.Event = field(default_factory=asyncio.Event)

    async def get_task(self, request: web.Request) -> web.Response:
        function = request.query["function"]
        self.polls.append(function)
        if self.broker_unavailable:
            return web.Response(status=503, text="Broker unavailable")
        queued = self.tasks.get(function)
        return web.json_response(queued.pop(0) if queued else {})

    async def feed(self, request: web.Request) -> web.Response:
        self.feed_started.set()
        await self.release_feed.wait()
        return web.Response(
            text="""<rss version="2.0"><channel><item>
            <title>Local item</title><link>https://example.test/item</link>
            <description>Local content</description>
            <pubDate>Thu, 22 Oct 2026 12:00:00 GMT</pubDate>
            <guid>local-item</guid></item></channel></rss>""",
            content_type="application/rss+xml",
        )

    async def submit_result(self, request: web.Request) -> web.Response:
        self.results.append(await request.json())
        self.result_submitted.set()
        return web.json_response({})

    async def grid_status(self, request: web.Request) -> web.Response:
        return web.json_response({"value": {"ready": True, "nodes": []}})


@pytest.fixture
async def boundary() -> AsyncIterator[WorkerBoundary]:
    boundary = WorkerBoundary()
    app = web.Application()
    app.router.add_get("/get_task", boundary.get_task)
    app.router.add_get("/feed", boundary.feed)
    app.router.add_get("/status", boundary.grid_status)
    app.router.add_post("/submit_result", boundary.submit_result)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    boundary.url = f"http://127.0.0.1:{runner.addresses[0][1]}"
    try:
        yield boundary
    finally:
        boundary.release_feed.set()
        await runner.cleanup()


@pytest.fixture
async def start_worker(boundary: WorkerBoundary):
    processes: list[asyncio.subprocess.Process] = []

    async def start(module: str) -> asyncio.subprocess.Process:
        env = {
            **os.environ,
            "DB_URL": "sqlite:///:memory:",
            "TWITCH_CLIENT_ID": "dummy",
            "TWITCH_CLIENT_SECRET": "dummy",
            "REDIS_HOST": "localhost",
            "BROKER_URL": boundary.url,
            "SELENIUM_DOCKER_URL": boundary.url,
        }
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            module,
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        processes.append(process)
        return process

    yield start
    for process in processes:
        if process.returncode is None:
            process.kill()
        await process.communicate()


async def wait_for_polls(boundary: WorkerBoundary, count: int) -> None:
    async with asyncio.timeout(60):
        while len(boundary.polls) < count:
            await asyncio.sleep(0.01)


async def assert_clean_exit(process: asyncio.subprocess.Process) -> None:
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
    assert process.returncode == 0, (stdout.decode(), stderr.decode())
    assert b"Unclosed" not in stderr
    assert b"Traceback" not in stderr


@pytest.mark.parametrize(
    ("module", "parser_ids", "signum"),
    [
        ("app.run.worker_light", light_parsers, signal.SIGTERM),
        ("app.run.worker_heavy", heavy_parsers, signal.SIGINT),
    ],
)
async def test_entrypoints_repeat_their_own_queues(
    start_worker, boundary, module, parser_ids, signum
):
    process = await start_worker(module)
    expected = [f"gkfeed.process_feed_{parser_id}" for parser_id in parser_ids]
    await wait_for_polls(boundary, len(expected) + 1)
    assert set(boundary.polls) == set(expected)
    if module == "app.run.worker_heavy":
        assert boundary.polls[: len(expected)] == expected
        assert boundary.polls[len(expected)] == expected[0]
    process.send_signal(signum)
    await assert_clean_exit(process)


async def test_light_shutdown_drains_claimed_feed_and_ignores_further_signals(
    start_worker, boundary
):
    boundary.tasks["gkfeed.process_feed_web"] = [
        {
            "task_id": "local-feed",
            "function": "gkfeed.process_feed_web",
            "data": [
                json.dumps(
                    {
                        "id": 1,
                        "title": "Local feed",
                        "url": f"{boundary.url}/feed",
                        "type": "web",
                    }
                )
            ],
        }
    ]
    process = await start_worker("app.run.worker_light")
    await asyncio.wait_for(boundary.feed_started.wait(), timeout=10)
    process.send_signal(signal.SIGTERM)
    await asyncio.sleep(0.1)
    polls_at_shutdown = len(boundary.polls)
    process.send_signal(signal.SIGINT)
    await asyncio.sleep(0.1)
    assert process.returncode is None
    assert len(boundary.polls) == polls_at_shutdown
    boundary.release_feed.set()
    await asyncio.wait_for(boundary.result_submitted.wait(), timeout=10)
    await assert_clean_exit(process)
    assert len(boundary.results) == 1
    assert boundary.results[0]["task_id"] == "local-feed"
    result = json.loads(boundary.results[0]["result"])
    assert result["items"][0]["title"] == "Local item"
    assert result["items"][0]["hash"]


async def test_heavy_entrypoint_propagates_broker_failure(start_worker, boundary):
    boundary.broker_unavailable = True
    process = await start_worker("app.run.worker_heavy")
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
    assert process.returncode != 0, stdout.decode()
    assert b"Traceback" in stderr
    assert not boundary.results
