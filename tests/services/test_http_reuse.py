import asyncio
from dataclasses import dataclass, field

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from app.services.http import HttpRequestError, HttpService


@dataclass
class HttpBoundary:
    transports: set = field(default_factory=set)
    requests: list = field(default_factory=list)
    active: int = 0
    peak: int = 0
    url: str = ""

    async def handle(self, request):
        self.transports.add(request.transport)
        self.requests.append((request.method, dict(request.headers)))
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await request.read()
            await asyncio.sleep(0.01)
            response = web.json_response({"ok": True})
            response.set_cookie("feed_auth", "secret")
            return response
        finally:
            self.active -= 1


@pytest.fixture
async def http_boundary():
    boundary = HttpBoundary()
    app = web.Application()
    app.router.add_route("*", "/", boundary.handle)
    async with TestServer(app) as server:
        # A hostname allows cookies in a regular CookieJar, unlike an IP URL.
        boundary.url = str(server.make_url("/").with_host("localhost"))
        yield boundary


async def assert_closed(transports):
    async with asyncio.timeout(1):
        while any(not transport.is_closing() for transport in transports):
            await asyncio.sleep(0.01)


async def test_repeated_requests_reuse_connection_and_close_pool(http_boundary):
    async with HttpService():
        assert await HttpService.get(http_boundary.url)
        assert await HttpService.get_json(http_boundary.url) == {"ok": True}
        assert await HttpService.post(http_boundary.url, {"a": "b"})
        assert await HttpService.post_json(http_boundary.url, {"a": "b"})
        assert await HttpService.delete(http_boundary.url)
        assert await HttpService.get_status(http_boundary.url) == 200
    assert len(http_boundary.requests) == 6
    assert len(http_boundary.transports) == 1
    await assert_closed(http_boundary.transports)


async def test_nested_scope_and_requests_do_not_share_credentials(http_boundary):
    async with HttpService():
        await HttpService.get(
            http_boundary.url, headers={"Authorization": "Bearer first-feed"}
        )
        async with HttpService():
            await HttpService.get(http_boundary.url)
        await HttpService.get(http_boundary.url, headers={"X-Feed": "third"})
    headers = [headers for _, headers in http_boundary.requests]
    assert headers[0]["Authorization"] == "Bearer first-feed"
    assert "Authorization" not in headers[1]
    assert "Authorization" not in headers[2]
    assert all("Cookie" not in request_headers for request_headers in headers)
    assert headers[1]["User-Agent"] == HttpService.headers["User-Agent"]
    assert headers[2]["X-Feed"] == "third"
    assert len(http_boundary.transports) == 1
    await assert_closed(http_boundary.transports)


async def test_pool_limits_concurrent_requests_per_host(http_boundary):
    async with HttpService(connection_limit=2, per_host_limit=1):
        await asyncio.gather(*(HttpService.get(http_boundary.url) for _ in range(6)))
    assert len(http_boundary.requests) == 6
    assert http_boundary.peak == 1
    assert len(http_boundary.transports) == 1
    await assert_closed(http_boundary.transports)


async def test_pool_limits_concurrent_requests_across_hosts(http_boundary):
    app = web.Application()
    app.router.add_get("/", http_boundary.handle)
    async with (
        TestServer(app) as other_server,
        HttpService(connection_limit=1, per_host_limit=10),
    ):
        urls = [http_boundary.url, str(other_server.make_url("/"))] * 3
        await asyncio.gather(*(HttpService.get(url) for url in urls))
    assert len(http_boundary.requests) == 6
    assert http_boundary.peak == 1
    assert len(http_boundary.transports) == 2
    await assert_closed(http_boundary.transports)


async def test_scope_closes_after_error_and_next_scope_is_independent(http_boundary):
    with pytest.raises(HttpRequestError, match="size limit"):
        async with HttpService():
            await HttpService.get_response(http_boundary.url, max_bytes=1)
    previous = set(http_boundary.transports)
    await assert_closed(previous)
    async with HttpService():
        await HttpService.get(http_boundary.url)
    assert len(http_boundary.transports) == 2
    await assert_closed(http_boundary.transports)


async def test_scope_closes_when_owner_is_cancelled(http_boundary):
    requested = asyncio.Event()

    async def owner():
        async with HttpService():
            await HttpService.get(http_boundary.url)
            requested.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(owner())
    await asyncio.wait_for(requested.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await assert_closed(http_boundary.transports)


async def test_unscoped_requests_close_connections(http_boundary):
    await HttpService.get(http_boundary.url)
    await HttpService.get(http_boundary.url)
    assert len(http_boundary.transports) == 2
    await assert_closed(http_boundary.transports)
