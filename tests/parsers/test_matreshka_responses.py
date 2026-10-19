import json
from collections import Counter
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import NotRequired, TypedDict

import pytest

from app.extensions.parsers.exceptions import FeedUnavailable
from app.parsers.matreshka import MatreshkaFeed
from app.serializers.feed import Feed, Item
from app.utils.datetime import constant_datetime


class ServerState(TypedDict):
    html: str
    payload: object
    status: int
    raw: NotRequired[bytes]


@pytest.fixture
def matreshka_server():
    state: ServerState = {
        "html": "<title> Channel | Matreshka </title>",
        "payload": {"data": []},
        "status": 200,
    }
    requests = Counter()
    posts = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests[self.path] += 1
            self.respond(200, state["html"].encode(), "text/html; charset=utf-8")

        def do_POST(self):
            requests[self.path] += 1
            body = self.rfile.read(int(self.headers["Content-Length"]))
            posts.append((self.path, json.loads(body), self.headers))
            payload = state.get("raw", json.dumps(state["payload"]).encode())
            self.respond(state["status"], payload, "application/json")

        def respond(self, status, body, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state, requests, posts
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def parser_for(base_url):
    return MatreshkaFeed(
        Feed(
            id=1,
            title="Matreshka",
            type="matreshka",
            url=base_url + "/channel/channel-id/internal/videos",
        ),
        {},
    )


async def test_matreshka_preserves_items_and_request_contract(matreshka_server):
    base_url, state, requests, posts = matreshka_server
    videos = [{"id": f"video-{index}", "name": f"Video {index}"} for index in range(12)]
    state["payload"] = {"data": videos}
    parser = parser_for(base_url)

    items = await parser.apply_hashes(await parser.items)

    assert items == [
        Item(
            title=f"Channel - {video['name']}",
            text=f"Channel - {video['name']}",
            link=f"{base_url}/video/{video['id']}",
            date=constant_datetime,
            hash=sha256(f"{base_url}/video/{video['id']}".encode()).hexdigest(),
        )
        for video in videos
    ]
    path, body, headers = posts[0]
    assert path == "/api/v2/video"
    assert body == {
        "field_mask": ["id", "name"],
        "filter": [{"field": "channel_id", "is": "=", "value": "channel-id"}],
        "scope": ["public"],
        "page": 1,
        "per_page": 12,
        "sort": {"field": "published_at", "direction": "desc"},
    }
    assert headers["Origin"] == base_url
    assert headers["Referer"] == parser.feed.url
    assert headers["X-Request-Context"] == "default"

    state["html"] = "<title>Changed channel</title>"
    state["payload"] = {"data": [{"id": "video-0", "name": "Renamed video"}]}
    renamed = await parser.apply_hashes(await parser.items)

    assert renamed[0].title == "Channel - Renamed video"
    assert renamed[0].link == items[0].link
    assert renamed[0].hash == items[0].hash
    assert requests["/channel/channel-id/internal/videos"] == 1
    assert requests["/api/v2/video"] == 2


async def test_matreshka_accepts_explicitly_empty_data(matreshka_server):
    base_url, _, _, _ = matreshka_server

    assert await parser_for(base_url).items == []


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        (None, "expected an object"),
        ([], "expected an object"),
        ("error", "expected an object"),
        ({"error": "upstream failure"}, "missing 'data'"),
        ({"data": None}, "'data' must be a list"),
        ({"data": {}}, "'data' must be a list"),
        ({"data": ""}, "'data' must be a list"),
        ({"data": False}, "'data' must be a list"),
    ],
)
async def test_matreshka_rejects_invalid_api_response(
    matreshka_server, payload, reason
):
    base_url, state, _, _ = matreshka_server
    state["payload"] = payload

    with pytest.raises(ValueError, match=reason):
        await parser_for(base_url).items


@pytest.mark.parametrize(
    ("video", "reason"),
    [
        (None, "expected an object"),
        ([], "expected an object"),
        ("video", "expected an object"),
        ({"name": "Video"}, "'id' must be a non-empty string"),
        ({"id": None, "name": "Video"}, "'id' must be a non-empty string"),
        ({"id": "", "name": "Video"}, "'id' must be a non-empty string"),
        ({"id": "  ", "name": "Video"}, "'id' must be a non-empty string"),
        ({"id": 123, "name": "Video"}, "'id' must be a non-empty string"),
        ({"id": True, "name": "Video"}, "'id' must be a non-empty string"),
        ({"id": {}, "name": "Video"}, "'id' must be a non-empty string"),
        ({"id": "video-id"}, "'name' must be a non-empty string"),
        ({"id": "video-id", "name": None}, "'name' must be a non-empty string"),
        ({"id": "video-id", "name": ""}, "'name' must be a non-empty string"),
        ({"id": "video-id", "name": "  "}, "'name' must be a non-empty string"),
        ({"id": "video-id", "name": 123}, "'name' must be a non-empty string"),
        ({"id": "video-id", "name": True}, "'name' must be a non-empty string"),
        ({"id": "video-id", "name": ["Video"]}, "'name' must be a non-empty string"),
    ],
)
async def test_matreshka_rejects_entire_batch_with_damaged_video(
    matreshka_server, video, reason
):
    base_url, state, _, _ = matreshka_server
    state["payload"] = {"data": [{"id": "valid-video", "name": "Valid video"}, video]}
    parser = parser_for(base_url)

    with pytest.raises(ValueError, match=rf"data\[1\].*{reason}"):
        await parser.items

    state["payload"] = {"data": [{"id": "valid-video", "name": "Valid video"}]}
    assert len(await parser.items) == 1


async def test_matreshka_rejects_invalid_json(matreshka_server):
    base_url, state, _, _ = matreshka_server
    state["raw"] = b'{"data":'

    with pytest.raises(ValueError, match="Matreshka API response: expected valid JSON"):
        await parser_for(base_url).items


@pytest.mark.parametrize("status", [403, 404, 405, 429, 503])
async def test_matreshka_reports_api_unavailability(matreshka_server, status):
    base_url, state, _, _ = matreshka_server
    state["status"] = status
    parser = parser_for(base_url)

    with pytest.raises(FeedUnavailable) as error:
        await parser.items

    assert error.value.url == parser.feed.url
    assert error.value.reason == "http_request_failed"
    assert error.value.retry_at is None

    state["status"] = 200
    assert await parser.items == []


@pytest.mark.parametrize(
    "html",
    [
        "<h1>Internal server error</h1>",
        "<title></title>",
        "<title>  | Matreshka</title>",
    ],
)
async def test_matreshka_requires_channel_title(matreshka_server, html):
    base_url, state, _, posts = matreshka_server
    state["html"] = html
    state["payload"] = {"data": [{"id": "video-id", "name": "Video"}]}

    with pytest.raises(ValueError, match="Could not find Matreshka channel title"):
        await parser_for(base_url).items

    assert posts == []
