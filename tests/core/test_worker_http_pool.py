import asyncio
import signal
from dataclasses import dataclass, field

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from tests.core import test_worker_entrypoints

start_worker = test_worker_entrypoints.start_worker


@dataclass
class WorkerHttpBoundary:
    url: str = ""
    transports: set = field(default_factory=set)
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    polls: int = 0

    async def get_task(self, request):
        self.transports.add(request.transport)
        self.polls += 1
        if self.polls >= 3:
            self.ready.set()
        return web.json_response({"task_id": None})

    async def status(self, request):
        return web.json_response({"value": {"ready": True, "nodes": []}})


@pytest.fixture
async def boundary():
    boundary = WorkerHttpBoundary()
    app = web.Application()
    app.router.add_get("/get_task", boundary.get_task)
    app.router.add_get("/status", boundary.status)
    async with TestServer(app) as server:
        boundary.url = str(server.make_url("/")).rstrip("/")
        yield boundary


@pytest.mark.parametrize("module", ["app.run.worker_light", "app.run.worker_heavy"])
async def test_worker_process_reuses_broker_connection_and_closes_it(
    start_worker, boundary, module
):
    process = await start_worker(module)
    await asyncio.wait_for(boundary.ready.wait(), 10)
    assert boundary.polls >= 3
    assert len(boundary.transports) == 1
    process.send_signal(signal.SIGTERM)
    await test_worker_entrypoints.assert_clean_exit(process)
    async with asyncio.timeout(1):
        while any(not transport.is_closing() for transport in boundary.transports):
            await asyncio.sleep(0.01)
