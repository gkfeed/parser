import asyncio
import json
import socket
from urllib.parse import parse_qs

import aiohttp
import pytest
from aiohttp import web

from app.extensions.parsers.exceptions import FeedUnavailable
from app.services.http import HttpRequestError, HttpService
from app.services.twitch import Twitch
from app.services.twitch.exceptions import TwitchResponseError

pytestmark = pytest.mark.integration

BINARY_BODY = b"\x00\xffHTTP bytes\r\n"
JSON_BODY = {"message": "ok", "values": [1, 2]}
PUBLIC_REQUESTS = [
    ("get", ()),
    ("get_with_status", ()),
    ("get_response", ()),
    ("post", ({"field": "value"},)),
    ("delete", ()),
    ("get_json", ()),
    ("post_json", ({"field": "value"},)),
    ("get_status", ()),
]


@pytest.fixture
async def http_server():
    requests = []
    body_started = asyncio.Event()
    finish_body = asyncio.Event()

    async def respond(request):
        requests.append((request.method, dict(request.headers), await request.read()))
        if request.path == "/disconnect":
            request.transport.abort()
            return web.Response()
        if request.path == "/truncated":
            response = web.StreamResponse(headers={"Content-Length": "100"})
            await response.prepare(request)
            await response.write(b"{")
            request.transport.abort()
            return response
        if request.path == "/pending":
            response = web.StreamResponse(headers={"Content-Length": "1"})
            await response.prepare(request)
            body_started.set()
            await finish_body.wait()
            return response
        if request.path.startswith("/status/"):
            return web.json_response(
                {"error": "failure"}, status=int(request.path.rsplit("/", 1)[1])
            )
        if request.path == "/invalid-json":
            return web.Response(body=b"{broken", content_type="application/json")
        if request.path == "/nonobject":
            return web.json_response([])
        if request.path == "/plain-json":
            return web.Response(text=json.dumps(JSON_BODY))
        if request.path == "/encoded-json":
            return web.Response(
                body='{"message": "Привет"}'.encode("cp1251"),
                content_type="application/json",
                charset="windows-1251",
            )
        if request.path == "/json":
            return web.json_response(JSON_BODY)
        return web.Response(body=BINARY_BODY, headers={"X-Trace": "fixture"})

    app = web.Application()
    app.router.add_route("*", "/{path:.*}", respond)
    runner = web.AppRunner(app)
    await runner.setup()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    await web.SockSite(runner, listener).start()
    try:
        yield f"http://127.0.0.1:{port}", requests, body_started
    finally:
        finish_body.set()
        await runner.cleanup()


async def test_byte_and_metadata_contracts(http_server):
    base_url, requests, _ = http_server
    headers = {"X-Caller": "bytes"}

    assert await HttpService.get(base_url + "/bytes", headers) == BINARY_BODY
    assert await HttpService.get_with_status(base_url + "/bytes") == (200, BINARY_BODY)
    response = await HttpService.get_response(base_url + "/bytes")

    assert response.status == 200
    assert response.content == BINARY_BODY
    assert response.headers["x-trace"] == "fixture"
    assert response.headers["content-type"] == "application/octet-stream"
    assert requests[0][1]["X-Caller"] == "bytes"


async def test_post_form_and_delete_preserve_bytes(http_server):
    base_url, requests, _ = http_server

    assert (
        await HttpService.post(
            base_url + "/bytes", {"field": "a b", "count": "2"}, headers=None
        )
        == BINARY_BODY
    )
    assert await HttpService.delete(base_url + "/bytes") == BINARY_BODY

    method, headers, body = requests[0]
    assert method == "POST"
    assert headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert parse_qs(body.decode()) == {"field": ["a b"], "count": ["2"]}
    assert requests[1][0] == "DELETE"


async def test_json_requests_preserve_payloads_and_headers(http_server):
    base_url, requests, _ = http_server
    payload = {"nested": {"value": [1, True, None]}}

    assert await HttpService.get_json(base_url + "/json") == JSON_BODY
    assert (
        await HttpService.post_json(
            base_url + "/json", payload, headers={"X-Caller": "json"}
        )
        == JSON_BODY
    )

    method, headers, body = requests[1]
    assert method == "POST"
    assert headers["X-Caller"] == "json"
    assert headers["Content-Type"] == "application/json"
    assert json.loads(body) == payload
    assert await HttpService.get_json(base_url + "/encoded-json") == {
        "message": "Привет"
    }


@pytest.mark.parametrize("status", [200, 404, 429, 500])
async def test_raw_responses_and_status_expose_http_errors(http_server, status):
    base_url, _, _ = http_server
    url = f"{base_url}/status/{status}"

    assert await HttpService.get_status(url) == status
    raw_status, content = await HttpService.get_with_status(url)
    response = await HttpService.get_response(url)

    assert raw_status == response.status == status
    assert json.loads(content) == json.loads(response.content) == {"error": "failure"}


@pytest.mark.parametrize(
    ("method", "args"),
    [
        entry
        for entry in PUBLIC_REQUESTS
        if entry[0] not in {"get_with_status", "get_response", "get_status"}
    ],
)
@pytest.mark.parametrize("status", [404, 429, 500])
async def test_data_methods_reject_error_statuses(http_server, method, args, status):
    base_url, _, _ = http_server

    with pytest.raises(HttpRequestError) as raised:
        await getattr(HttpService, method)(f"{base_url}/status/{status}", *args)

    assert raised.value.status == status


@pytest.mark.parametrize(("method", "args"), PUBLIC_REQUESTS)
async def test_connection_refused_is_translated_for_every_method(method, args):
    # Keep the port bound without listening so no other process can claim it.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        with pytest.raises(HttpRequestError) as raised:
            await getattr(HttpService, method)(url, *args)

    assert raised.value.status is None
    assert isinstance(raised.value.__cause__, aiohttp.ClientConnectorError)


@pytest.mark.parametrize(("method", "args"), PUBLIC_REQUESTS)
async def test_disconnected_server_is_translated_for_every_method(
    http_server, method, args
):
    base_url, _, _ = http_server

    with pytest.raises(HttpRequestError) as raised:
        await getattr(HttpService, method)(base_url + "/disconnect", *args)

    assert raised.value.status is None
    assert isinstance(raised.value.__cause__, aiohttp.ClientError)


@pytest.mark.parametrize(("method", "args"), PUBLIC_REQUESTS)
async def test_invalid_url_is_translated_for_every_method(method, args):
    with pytest.raises(HttpRequestError) as raised:
        await getattr(HttpService, method)("http://[invalid", *args)

    assert raised.value.status is None
    assert isinstance(raised.value.__cause__, aiohttp.InvalidURL)


@pytest.mark.parametrize(
    ("method", "args"),
    [entry for entry in PUBLIC_REQUESTS if entry[0] != "get_status"],
)
async def test_incomplete_body_is_translated(http_server, method, args):
    base_url, _, _ = http_server

    with pytest.raises(HttpRequestError) as raised:
        await getattr(HttpService, method)(base_url + "/truncated", *args)

    assert isinstance(raised.value.__cause__, aiohttp.ClientError)


@pytest.mark.parametrize(("method", "args"), [("get_json", ()), ("post_json", ({},))])
async def test_malformed_json_raises_decode_error(http_server, method, args):
    base_url, _, _ = http_server

    with pytest.raises(json.JSONDecodeError):
        await getattr(HttpService, method)(base_url + "/invalid-json", *args)


async def test_limited_reads_reject_oversized_responses(http_server):
    base_url, _, _ = http_server

    response = await HttpService.get_response(
        base_url + "/bytes", max_bytes=len(BINARY_BODY)
    )
    assert response.content == BINARY_BODY
    with pytest.raises(HttpRequestError, match="size limit"):
        await HttpService.get_response(base_url + "/bytes", max_bytes=1)


async def test_cancellation_is_not_translated(http_server):
    base_url, _, body_started = http_server
    request = asyncio.create_task(HttpService.get(base_url + "/pending"))
    await asyncio.wait_for(body_started.wait(), timeout=5)
    request.cancel()

    with pytest.raises(asyncio.CancelledError):
        await request

    assert await HttpService.get(base_url + "/bytes") == BINARY_BODY


async def test_status_does_not_wait_for_body(http_server):
    base_url, _, _ = http_server

    assert (
        await asyncio.wait_for(HttpService.get_status(base_url + "/pending"), timeout=5)
        == 200
    )


async def test_twitch_json_accepts_payload_without_json_content_type(http_server):
    base_url, requests, _ = http_server

    assert (
        await Twitch.get_json(
            base_url + "/plain-json", {"Authorization": "Bearer local-token"}
        )
        == JSON_BODY
    )
    assert requests[0][1]["Authorization"] == "Bearer local-token"


@pytest.mark.parametrize(
    ("path", "error", "message"),
    [
        ("/status/201", FeedUnavailable, "twitch_http_201"),
        ("/status/401", FeedUnavailable, "twitch_http_401"),
        ("/status/500", FeedUnavailable, "twitch_http_500"),
        ("/disconnect", FeedUnavailable, "twitch_request_failed"),
        ("/invalid-json", TwitchResponseError, "invalid JSON"),
        ("/nonobject", TwitchResponseError, "expected an object"),
    ],
)
async def test_twitch_preserves_failure_contracts(http_server, path, error, message):
    base_url, _, _ = http_server

    with pytest.raises(error, match=message):
        await Twitch.get_json(base_url + path, {})
