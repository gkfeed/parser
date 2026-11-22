"""Exercise the HTTP pool and dispatcher against a local broker."""

import asyncio
import os
import signal
import sys
from contextlib import AsyncExitStack, suppress

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import create_async_engine

from app.models import Base
from app.models.feed import Feed as FeedModel
from app.serializers.feed import FeedResult
from app.services.http import HttpRequestError, HttpService

pytestmark = pytest.mark.integration


@pytest.fixture
async def local_server():
    connections = set()
    requests = []
    release = asyncio.Event()
    entered = asyncio.Event()

    async def handle(request):
        connections.add(request.transport)
        requests.append((request.path, dict(request.headers)))
        if request.path == "/redirect":
            response = web.HTTPFound("/redirect-next")
            response.set_cookie("hop", "present")
            raise response
        if request.path == "/redirect-next":
            assert request.cookies.get("hop") == "present"
            raise web.HTTPTemporaryRedirect("/final")
        if request.path == "/final":
            return web.Response(
                text=request.cookies.get("hop", "missing"), headers={"X-Test": "value"}
            )
        if request.path == "/hold":
            if sum(path == "/hold" for path, _ in requests) == 10:
                entered.set()
            await release.wait()
        if request.path == "/error":
            return web.Response(status=503)
        response = web.Response(text="ok")
        response.set_cookie("private", "secret")
        return response

    app = web.Application()
    app.router.add_route("*", "/{path:.*}", handle)
    async with TestServer(app, host="localhost") as server:
        yield server, connections, requests, entered, release
        release.set()


async def test_reuse_isolation_redirect_and_metadata(local_server):
    server, connections, requests, _, _ = local_server
    url = str(server.make_url("/"))
    for _ in range(12):
        assert await HttpService.get(url) == b"ok"
    assert len(connections) == 12
    connections.clear()
    requests.clear()

    async with HttpService.connection_pool():
        for _ in range(12):
            assert await HttpService.get(url) == b"ok"
        assert len(connections) == 1
        await HttpService.get(
            url, headers={"Authorization": "Bearer first", "Cookie": "manual=yes"}
        )
        await HttpService.get(url, headers={"Authorization": "Bearer second"})
        await HttpService.get(url)
        assert requests[-3][1]["Authorization"] == "Bearer first"
        assert requests[-3][1]["Cookie"] == "manual=yes"
        assert requests[-2][1]["Authorization"] == "Bearer second"
        assert "Cookie" not in requests[-2][1]
        assert "Authorization" not in requests[-1][1]
        assert "Cookie" not in requests[-1][1]

        await asyncio.gather(
            HttpService.get(url, headers={"Authorization": "Bearer concurrent-a"}),
            HttpService.get(url, headers={"Authorization": "Bearer concurrent-b"}),
        )
        assert {entry[1]["Authorization"] for entry in requests[-2:]} == {
            "Bearer concurrent-a",
            "Bearer concurrent-b",
        }
        assert all("Cookie" not in entry[1] for entry in requests[-2:])

        response = await HttpService.get_response(url + "redirect")
        assert response.status == 200
        assert response.content == b"present"
        assert response.url == url + "final"
        assert response.redirect_statuses == (302, 307)
        assert response.headers["x-test"] == "value"
        await HttpService.get(url)
        assert "Cookie" not in requests[-1][1]

    assert all(transport.is_closing() for transport in connections)


async def test_pool_limit_and_request_cancellation(local_server):
    server, connections, requests, entered, release = local_server
    url = str(server.make_url("/hold"))
    async with HttpService.connection_pool():
        tasks = [asyncio.create_task(HttpService.get(url)) for _ in range(11)]
        try:
            await asyncio.wait_for(entered.wait(), 5)
            await asyncio.sleep(0.1)
            assert len(requests) == 10
            assert len(connections) == 10
            tasks[-1].cancel()
            with pytest.raises(asyncio.CancelledError):
                await tasks[-1]
            release.set()
            assert await asyncio.gather(*tasks[:-1]) == [b"ok"] * 10
            assert await HttpService.get(str(server.make_url("/"))) == b"ok"
        finally:
            release.set()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    assert all(transport.is_closing() for transport in connections)


async def test_pool_total_limit_across_hosts():
    entered = asyncio.Event()
    release = asyncio.Event()
    arrivals = []

    async def handle(request):
        arrivals.append(request.host)
        if len(arrivals) == 100:
            entered.set()
        await release.wait()
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/", handle)
    async with AsyncExitStack() as stack:
        servers = [await stack.enter_async_context(TestServer(app)) for _ in range(11)]
        async with HttpService.connection_pool():
            tasks = [
                asyncio.create_task(HttpService.get(str(server.make_url("/"))))
                for server in servers
                for _ in range(10)
            ]
            try:
                await asyncio.wait_for(entered.wait(), 10)
                await asyncio.sleep(0.1)
                assert len(arrivals) == 100
                release.set()
                assert await asyncio.gather(*tasks) == [b"ok"] * 110
            finally:
                release.set()
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)


async def test_pool_closes_after_errors_and_cancellation(local_server):
    server, connections, _, _, _ = local_server
    url = str(server.make_url("/"))
    with pytest.raises(RuntimeError, match="stop"):
        async with HttpService.connection_pool():
            with pytest.raises(HttpRequestError) as error:
                await HttpService.get(url + "error")
            assert error.value.status == 503
            with pytest.raises(HttpRequestError):
                await HttpService.get_response(url, max_bytes=1)
            with pytest.raises(HttpRequestError) as error:
                await HttpService.post_json(url + "error", {})
            assert error.value.status == 503
            assert await HttpService.get(url) == b"ok"
            raise RuntimeError("stop")
    assert all(transport.is_closing() for transport in connections)
    connections.clear()

    ready = asyncio.Event()

    async def run():
        async with HttpService.connection_pool():
            await HttpService.get(url)
            ready.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(run())
    await asyncio.wait_for(ready.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert all(transport.is_closing() for transport in connections)
    await HttpService.get(url)
    assert len(connections) == 2


async def test_dispatcher_process_reuses_and_closes_broker_connection(tmp_path):
    requests = []
    connections = set()
    polling = asyncio.Event()
    release = asyncio.Event()

    async def enqueue(request):
        connections.add(request.transport)
        requests.append(request.path)
        return web.json_response({"task_id": "one"})

    async def result(request):
        connections.add(request.transport)
        requests.append(request.path)
        if requests.count("/result/one") == 3:
            polling.set()
            await release.wait()
        return web.json_response(
            {"status": "processing", "result": FeedResult(items=[]).model_dump_json()}
        )

    app = web.Application()
    app.router.add_post("/enqueue", enqueue)
    app.router.add_get("/result/{task_id}", result)
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'dispatcher.db'}"
    engine = create_async_engine(db_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(
            insert(FeedModel),
            [{"title": "feed", "url": "https://example.com", "type": "web"}],
        )
    await engine.dispose()
    async with TestServer(app) as server:
        env = os.environ | {
            "DB_URL": db_url,
            "BROKER_URL": str(server.make_url("/")),
            "TWITCH_CLIENT_ID": "test",
            "TWITCH_CLIENT_SECRET": "test",
            "REDIS_HOST": "localhost",
        }
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.run.dispatcher",
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await asyncio.wait_for(polling.wait(), 20)
            assert requests == ["/enqueue", "/result/one", "/result/one", "/result/one"]
            assert len(connections) == 1
            process.send_signal(signal.SIGINT)
            _, stderr = await asyncio.wait_for(process.communicate(), 10)
            assert process.returncode in (-signal.SIGINT, 130), stderr.decode()
            await asyncio.sleep(0.1)
            assert all(transport.is_closing() for transport in connections)
        finally:
            release.set()
            if process.returncode is None:
                process.kill()
                with suppress(ProcessLookupError):
                    await process.communicate()
