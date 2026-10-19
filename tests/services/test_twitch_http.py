import json
from datetime import UTC, datetime

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from app.extensions.parsers.exceptions import FeedUnavailable
from app.parsers.twitch import TwitchFeed
from app.serializers.feed import Feed
from app.services.twitch import Twitch
from app.services.twitch.auth import TwitchAuthenticator


@pytest.fixture
async def twitch_api(monkeypatch):
    responses = {
        "auth": web.json_response({"access_token": "local-token"}),
        "stream": web.json_response({"data": []}),
    }

    def respond(endpoint):
        response = responses[endpoint]
        return web.Response(
            status=response.status, body=response.body, headers=response.headers
        )

    async def authenticate(request):
        body = await request.json()
        assert body["grant_type"] == "client_credentials"
        return respond("auth")

    async def streams(request):
        assert request.query["user_login"] == "streamer"
        assert request.headers["Authorization"] == "Bearer local-token"
        assert "Client-ID" in request.headers
        return respond("stream")

    app = web.Application()
    app.router.add_post("/token", authenticate)
    app.router.add_get("/streams", streams)
    async with TestServer(app) as server:
        # Redirect only the endpoints; authentication and HTTP requests remain real.
        monkeypatch.setattr(
            TwitchAuthenticator,
            "_TwitchAuthenticator__base_url",
            str(server.make_url("/token")),
        )
        monkeypatch.setattr(
            Twitch, "_Twitch__base_url", str(server.make_url("/streams?user_login="))
        )
        yield responses


def twitch_feed():
    return TwitchFeed(
        Feed(id=1, title="Twitch", type="twitch", url="https://twitch.tv/streamer"),
        {},
    )


async def test_offline_stream(twitch_api):
    assert await Twitch.get_stream("streamer") is None
    assert await twitch_feed().items == []


async def test_live_stream_item(twitch_api):
    twitch_api["stream"] = web.json_response(
        {"data": [{"title": "Live title", "started_at": "2026-10-19T12:34:56Z"}]}
    )
    parser = twitch_feed()
    items = await parser.apply_hashes(await parser.items)

    assert len(items) == 1
    item = items[0]
    assert item.title == "streamer: Live title"
    assert item.text == "Live title"
    assert item.date == datetime(2026, 10, 19, 12, 34, 56, tzinfo=UTC)
    assert item.link == parser.feed.url
    assert item.hash is not None
    assert (await parser.apply_hashes(await parser.items))[0].hash == item.hash


@pytest.mark.parametrize("status", [204, 400, 401, 403, 404, 429, 500, 502, 503])
async def test_stream_http_errors(twitch_api, status):
    # Even an offline-shaped body must not hide an HTTP error.
    twitch_api["stream"] = web.Response(
        status=status, text='{"data": []}', content_type="application/json"
    )
    with pytest.raises(FeedUnavailable) as error:
        await twitch_feed().items

    assert error.value.reason == f"twitch_http_{status}"
    assert error.value.retry_at is None


@pytest.mark.parametrize("status", [401, 403, 500, 503])
async def test_authentication_http_errors(twitch_api, status):
    twitch_api["auth"] = web.Response(status=status, text="Authentication unavailable")
    with pytest.raises(FeedUnavailable) as error:
        await twitch_feed().items

    assert error.value.reason == "twitch_authentication_failed"


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        (None, "expected an object"),
        ([], "expected an object"),
        ({}, "data must be a list"),
        ({"error": "Unauthorized"}, "data must be a list"),
        ({"data": None}, "data must be a list"),
        ({"data": {}}, "data must be a list"),
        ({"data": "x"}, "data must be a list"),
        ({"data": [{}, {}]}, "expected at most one stream"),
        ({"data": [None]}, "stream must be an object"),
        ({"data": [{}]}, "title must be a string"),
        ({"data": [{"title": 123}]}, "title must be a string"),
        ({"data": [{"title": "Live"}]}, "started_at must be a string"),
        (
            {"data": [{"title": "Live", "started_at": 123}]},
            "started_at must be a string",
        ),
        ({"data": [{"title": "Live", "started_at": "invalid"}]}, "invalid started_at"),
    ],
)
async def test_invalid_stream_structure(twitch_api, payload, reason):
    twitch_api["stream"] = web.Response(
        text=json.dumps(payload), content_type="application/json"
    )
    with pytest.raises(ValueError, match=f"Invalid Twitch API response: {reason}"):
        await twitch_feed().items


@pytest.mark.parametrize("body", [b"{", b"", b"\xff"])
async def test_invalid_stream_json(twitch_api, body):
    twitch_api["stream"] = web.Response(body=body, content_type="application/json")
    with pytest.raises(ValueError, match="Invalid Twitch API response: invalid JSON"):
        await twitch_feed().items


async def test_stream_connection_failure(twitch_api, monkeypatch):
    app = web.Application()
    async with TestServer(app) as server:
        url = str(server.make_url("/streams?user_login="))
    monkeypatch.setattr(Twitch, "_Twitch__base_url", url)

    with pytest.raises(FeedUnavailable) as error:
        await twitch_feed().items

    assert error.value.reason == "twitch_request_failed"
