import asyncio
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from threading import Thread

import pytest
from aiohttp import web
from fakeredis import TcpFakeServer

from app.serializers.feed import Feed, FeedResult
from app.services.broker import BrokerService

pytestmark = pytest.mark.integration

_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>Worker integration feed</title>
<item><title>HTTP item</title><link>https://example.test/item</link>
<description>Parsed without a browser</description>
<pubDate>Mon, 12 Oct 2026 10:00:00 GMT</pubDate><guid>http-item</guid>
</item></channel></rss>"""
_HTML = """<html><head><title>Worker integration feed</title></head><body>
<h1>HTTP item</h1><div class="status-category"><div>available</div></div>
</body></html>"""


@dataclass
class BrokerFixture:
    url: str
    redis_host: str
    tasks: dict[str, dict] = field(default_factory=dict)
    slow_started: asyncio.Event = field(default_factory=asyncio.Event)
    release_slow: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def broker(self) -> BrokerService:
        return BrokerService(self.url)

    async def enqueue(self, task_id: str, parser: str, path: str) -> None:
        feed = Feed(
            id=len(self.tasks) + 1, title=task_id, url=self.url + path, type=parser
        )
        self.tasks[task_id] = {
            "task_id": task_id,
            "function": f"gkfeed.process_feed_{parser}",
            "data": [feed.model_dump_json()],
            "status": "pending",
            "result": None,
        }


@pytest.fixture
def isolated_cache(unused_tcp_port_factory):
    port = unused_tcp_port_factory()
    host = f"127.0.{port // 256}.{port % 256}"
    with TcpFakeServer((host, 6379), server_type="redis") as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield host
        finally:
            server.shutdown()
            thread.join(timeout=5)


@pytest.fixture
async def worker_broker(unused_tcp_port, isolated_cache):
    fixture = BrokerFixture(f"http://127.0.0.1:{unused_tcp_port}", isolated_cache)

    async def get_task(request):
        function = request.query["function"]
        for task in fixture.tasks.values():
            if task["function"] == function and task["status"] == "pending":
                task["status"] = "processing"
                return web.json_response(task)
        return web.json_response({"task_id": None})

    async def result(request):
        return web.json_response(fixture.tasks[request.match_info["task_id"]])

    async def submit_result(request):
        payload = await request.json()
        fixture.tasks[payload["task_id"]].update(
            status="completed", result=payload["result"]
        )
        return web.json_response({})

    async def submit_error(request):
        payload = await request.json()
        fixture.tasks[payload["task_id"]].update(
            status="failed", result=payload["error_message"]
        )
        return web.json_response({})

    async def rss(request):
        if request.path.startswith("/slow"):
            fixture.slow_started.set()
            await fixture.release_slow.wait()
        if request.path.endswith("http"):
            return web.Response(text=_HTML, content_type="text/html")
        return web.Response(text=_RSS, content_type="application/rss+xml")

    app = web.Application()
    app.router.add_get("/get_task", get_task)
    app.router.add_get("/result/{task_id}", result)
    app.router.add_post("/submit_result", submit_result)
    app.router.add_post("/submit_error", submit_error)
    app.router.add_get("/rss", rss)
    app.router.add_get("/slow", rss)
    app.router.add_get("/http", rss)
    app.router.add_get("/slow-http", rss)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", unused_tcp_port).start()
    try:
        yield fixture
    finally:
        fixture.release_slow.set()
        await runner.cleanup()


@pytest.fixture
async def start_http_worker(worker_broker):
    processes = []
    environment = {
        **os.environ,
        "DB_URL": "postgresql://dummy:dummy@127.0.0.1/worker_test",
        "TWITCH_CLIENT_ID": "dummy",
        "TWITCH_CLIENT_SECRET": "dummy",
        "REDIS_HOST": worker_broker.redis_host,
        "BROKER_URL": worker_broker.url,
        "SELENIUM_DOCKER_URL": "http://127.0.0.1:1",
    }

    async def start():
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.run.worker_http",
            cwd=Path(__file__).resolve().parents[2],
            env=environment,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        processes.append(process)
        return process

    try:
        yield start
    finally:
        for process in processes:
            await stop_worker(process)


async def stop_worker(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=10)
    except TimeoutError:
        process.kill()
        await process.wait()


async def poll_status(broker: BrokerService, task_id: str, status: str) -> dict:
    while True:
        task = await broker.get_task_data(task_id)
        if task["status"] == status:
            return task
        await asyncio.sleep(0.05)


async def wait_for_status(broker: BrokerService, task_id: str, status: str) -> dict:
    return await asyncio.wait_for(poll_status(broker, task_id, status), timeout=30)


async def test_http_worker_completes_feed_without_browser(
    worker_broker, start_http_worker
):
    await worker_broker.enqueue("browser-task", "spoti", "/rss")
    await worker_broker.enqueue("http-task", "yummyanime", "/http")
    await start_http_worker()

    task = await wait_for_status(worker_broker.broker, "http-task", "completed")

    result = FeedResult.model_validate_json(task["result"])
    assert len(result.items) == 1
    assert result.items[0].title == "HTTP item available"
    assert result.items[0].hash
    assert (await worker_broker.broker.get_task_data("browser-task"))["status"] == (
        "pending"
    )


async def test_http_worker_processes_only_one_feed_at_a_time(
    worker_broker, start_http_worker
):
    await worker_broker.enqueue("first", "yummyanime", "/slow-http")
    await worker_broker.enqueue("second", "yummyanime", "/http")
    await worker_broker.enqueue("light-task", "web", "/rss")
    await start_http_worker()
    await asyncio.wait_for(worker_broker.slow_started.wait(), timeout=10)

    assert (await worker_broker.broker.get_task_data("second"))["status"] == "pending"
    worker_broker.release_slow.set()
    await wait_for_status(worker_broker.broker, "first", "completed")
    await wait_for_status(worker_broker.broker, "second", "completed")
    assert (await worker_broker.broker.get_task_data("light-task"))[
        "status"
    ] == "pending"


@pytest.fixture
async def start_light_worker(worker_broker):
    processes = []

    async def start():
        environment = {
            **os.environ,
            "DB_URL": "postgresql://dummy:dummy@127.0.0.1/worker_test",
            "TWITCH_CLIENT_ID": "dummy",
            "TWITCH_CLIENT_SECRET": "dummy",
            "REDIS_HOST": worker_broker.redis_host,
            "BROKER_URL": worker_broker.url,
            "SELENIUM_DOCKER_URL": "http://127.0.0.1:1",
        }
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.run.worker_light",
            cwd=Path(__file__).resolve().parents[2],
            env=environment,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        processes.append(process)
        return process

    try:
        yield start
    finally:
        for process in processes:
            await stop_worker(process)


async def test_light_workers_process_concurrently_only_across_processes(
    worker_broker, start_light_worker
):
    await worker_broker.enqueue("first", "web", "/slow")
    await worker_broker.enqueue("second", "web", "/slow")
    await worker_broker.enqueue("third", "web", "/rss")
    await worker_broker.enqueue("http-task", "yummyanime", "/http")
    await worker_broker.enqueue("browser-task", "spoti", "/rss")
    await start_light_worker()

    await wait_for_status(worker_broker.broker, "first", "processing")
    await asyncio.wait_for(worker_broker.slow_started.wait(), timeout=10)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(
            poll_status(worker_broker.broker, "second", "processing"), timeout=5
        )
    assert (await worker_broker.broker.get_task_data("second"))["status"] == "pending"

    await start_light_worker()
    await wait_for_status(worker_broker.broker, "second", "processing")
    assert (await worker_broker.broker.get_task_data("third"))["status"] == "pending"

    worker_broker.release_slow.set()
    for task_id in ("first", "second", "third"):
        result = await wait_for_status(worker_broker.broker, task_id, "completed")
        assert FeedResult.model_validate_json(result["result"]).items[0].title == (
            "HTTP item"
        )
    for task_id in ("http-task", "browser-task"):
        assert (await worker_broker.broker.get_task_data(task_id))[
            "status"
        ] == "pending"
