import json
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

from app.extensions.parsers.exceptions import FeedUnavailable
from app.extensions.parsers.http import HttpParserExtension
from app.parsers.anilibria import AnilibriaFeed
from app.parsers.liquidpedia import LiquidpediaFeed
from app.parsers.mangalib import MangaLibFeed
from app.parsers.matreshka import MatreshkaFeed
from app.serializers.feed import Feed
from app.services.hash import HashService
from app.utils.datetime import constant_datetime

pytestmark = pytest.mark.integration


@pytest.fixture
def api_server():
    routes = {}
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.respond()

        def do_POST(self):
            self.respond()

        def respond(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            requests.append((self.command, self.path, dict(self.headers), body))
            payload = routes[urlsplit(self.path).path]
            if payload is None:
                self.close_connection = True
                return
            status, payload = payload if isinstance(payload, tuple) else (200, payload)
            content = (
                payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            )
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", routes, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class LocalTransport(HttpParserExtension):
    """Route site requests to a real server, keeping the parser's HTTP/cache path."""

    local_url: str

    async def _fetch_html(self, url):
        parsed = urlsplit(url)
        local = f"{self.local_url}/{parsed.netloc}{parsed.path}"
        if parsed.query:
            local += f"?{parsed.query}"
        return await super()._fetch_html(local)


class LocalAnilibria(LocalTransport, AnilibriaFeed):
    pass


class LocalMangaLib(LocalTransport, MangaLibFeed):
    pass


class LocalLiquidpedia(LocalTransport, LiquidpediaFeed):
    pass


def parser_for(parser_type, url, local_url=None):
    parser = parser_type(Feed(id=1, title="Test", type="test", url=url), {})
    parser.local_url = local_url
    return parser


def release():
    return {
        "name": {"main": "Series"},
        "episodes": [
            {
                "id": "one",
                "ordinal": 1,
                "name": "First",
                "preview": {"src": "/one.jpg"},
            },
            {"id": "two", "ordinal": 2, "preview": {"src": "https://img.test/two.jpg"}},
        ],
    }


def mirror_paths():
    return [
        f"/{host}/api/v1/anime/releases/series"
        for host in ("aniliberty.top", "anilibria.top", "api.anilibria.app")
    ]


async def test_anilibria_mirror_fallback_items_and_cache(api_server):
    base, routes, requests = api_server
    first, second, third = mirror_paths()
    routes[first] = b"invalid JSON"
    routes[second] = {"name": {"main": "Bad"}, "episodes": [{"id": "bad"}]}
    routes[third] = release()
    parser = parser_for(
        LocalAnilibria, "https://anilibria.top/release/series/episodes", base
    )

    items = await parser.apply_hashes(await parser.items)
    assert [item.title for item in items] == [
        "Series 2 эпизод",
        "Series 1 эпизод — First",
    ]
    assert items[0].link == "https://anilibria.top/anime/video/episode/two"
    assert 'src="https://img.test/two.jpg"' in items[0].text
    assert 'src="https://cdn.anilibria.top/one.jpg"' in items[1].text
    assert all(item.date == constant_datetime for item in items)
    assert await parser.apply_hashes(await parser.items) == items
    assert [request[1] for request in requests] == [first, second, third]
    assert parser.data["cache_storage_time"] == timedelta(seconds=5)
    assert parser.data["cache_storage_time_if_success"] == timedelta(days=1)


@pytest.mark.parametrize("payload, error", [(None, FeedUnavailable), ({}, ValueError)])
async def test_anilibria_mirrors_report_failure(api_server, payload, error):
    base, routes, requests = api_server
    routes.update(dict.fromkeys(mirror_paths(), payload))
    parser = parser_for(LocalAnilibria, "https://anilibria.top/release/series", base)
    with pytest.raises(error):
        await parser.items
    assert {request[1] for request in requests} == set(mirror_paths())


async def test_mangalib_limit_order_headers_dates_and_cache(api_server):
    base, routes, requests = api_server
    path = "/api.cdnlibs.org/api/manga/123--series/chapters"
    routes[path] = {
        "data": [
            {
                "volume": "2",
                "number": str(i),
                "name": "Chapter",
                "branches": [{"created_at": "2026-01-02T03:04:05+03:00"}],
            }
            for i in range(1, 8)
        ]
    }
    parser = parser_for(
        LocalMangaLib, "https://mangalib.org/ru/manga/123--series?x=1", base
    )
    items = await parser.apply_hashes(await parser.items)
    assert [item.link.rsplit("/", 1)[-1] for item in items] == [
        "c7",
        "c6",
        "c5",
        "c4",
        "c3",
    ]
    assert items[0].title == items[0].text == "Том 2, Глава 7 — Chapter"
    assert items[0].link == "https://mangalib.org/ru/123--series/read/v2/c7"
    assert items[0].date == datetime.fromisoformat("2026-01-02T03:04:05+03:00")
    assert await parser.apply_hashes(await parser.items) == items
    assert len(requests) == 1
    assert requests[0][2]["Site-Id"] == "1"
    assert requests[0][2]["Referer"] == "https://mangalib.org/"
    assert requests[0][2]["Accept"] == "application/json"
    assert parser.data["cache_storage_time"] == timedelta(hours=1)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"data": [None]},
        {"data": [{"volume": "1", "number": "2", "branches": [{"created_at": "bad"}]}]},
        b"\xff",
    ],
)
async def test_mangalib_rejects_malformed_payload(api_server, payload):
    base, routes, _ = api_server
    routes["/api.cdnlibs.org/api/manga/series/chapters"] = payload
    parser = parser_for(LocalMangaLib, "https://mangalib.org/ru/manga/series", base)
    with pytest.raises(ValueError):
        await parser.items


MATCH = """<h2><span id="Upcoming_Matches">Upcoming Matches</span></h2><div>
<div class="match-info" data-timestamp="1767225600000">
<div class="match-info-opponent-row"><span class="name">Team Spirit</span></div>
<div class="match-info-opponent-row"><span class="name">Opponent</span></div>
<a href="/dota2/Match:123">Match</a></div></div>"""
RECENT = """<div class="match-table-wrapper"><div class="table2__row--body">
<div class="block-team"><span class="name">Opponent</span></div>
<time datetime="2026-01-01T00:00:00"></time></div></div>"""


@pytest.mark.parametrize(
    "legacy, recent", [(False, False), (True, False), (True, True)]
)
async def test_liquidpedia_payloads_url_dates_fallback_and_cache(
    api_server, legacy, recent
):
    base, routes, requests = api_server
    html = RECENT if recent else MATCH
    routes["/liquipedia.net/dota2/api.php"] = {
        "parse": {"text": {"*": html} if legacy else html}
    }
    url = "https://liquipedia.net/dota2/index.php?title=Team_Spirit"
    parser = parser_for(LocalLiquidpedia, url, base)
    items = await parser.apply_hashes(await parser.items)
    assert len(items) == 1
    assert items[0].title == "Team Spirit vs Opponent"
    assert items[0].date == datetime(2026, 1, 1, tzinfo=UTC)
    assert items[0].link == (
        url if recent else "https://liquipedia.net/dota2/Match:123"
    )
    assert await parser.apply_hashes(await parser.items) == items
    assert len(requests) == 1
    query = parse_qs(urlsplit(requests[0][1]).query)
    assert query == {
        "action": ["parse"],
        "page": ["Team_Spirit"],
        "prop": ["text"],
        "format": ["json"],
        "formatversion": ["2"],
    }
    assert (
        requests[0][2]["User-Agent"]
        == "gkfeed-parser/0.1 (https://github.com/gkfeed/parser)"
    )


@pytest.mark.parametrize(
    "payload", [{"error": {"code": "bad"}}, {"parse": {"text": {}}}, b"\xff", []]
)
async def test_liquidpedia_rejects_malformed_payload(api_server, payload):
    base, routes, _ = api_server
    routes["/liquipedia.net/dota2/api.php"] = payload
    parser = parser_for(
        LocalLiquidpedia, "https://liquipedia.net/dota2/Team_Spirit", base
    )
    with pytest.raises(ValueError):
        await parser.items


@pytest.mark.parametrize(
    "parser_type, url, path, payload",
    [
        (
            LocalAnilibria,
            "https://anilibria.top/release/series",
            mirror_paths()[0],
            {"name": {"main": "Series"}, "episodes": []},
        ),
        (
            LocalMangaLib,
            "https://mangalib.org/ru/manga/series",
            "/api.cdnlibs.org/api/manga/series/chapters",
            {"data": []},
        ),
        (
            LocalLiquidpedia,
            "https://liquipedia.net/dota2/Team_Spirit",
            "/liquipedia.net/dota2/api.php",
            {"parse": {"text": "<p>No matches</p>"}},
        ),
    ],
)
async def test_valid_empty_payload(api_server, parser_type, url, path, payload):
    base, routes, _ = api_server
    routes[path] = payload
    assert await parser_for(parser_type, url, base).items == []


async def test_matreshka_request_items_hash_and_page_cache(api_server):
    base, routes, requests = api_server
    path = "/channel/channel-id/internal/videos"
    routes[path] = b"<title>Channel | Matreshka</title>"
    routes["/api/v2/video"] = {
        "data": [{"id": "two", "name": "Second"}, {"id": "one", "name": "First"}]
    }
    parser = parser_for(MatreshkaFeed, base + path)
    items = await parser.apply_hashes(await parser.items)
    assert [item.title for item in items] == ["Channel - Second", "Channel - First"]
    assert [item.link for item in items] == [base + "/video/two", base + "/video/one"]
    assert all(item.date == constant_datetime for item in items)
    assert items[0].hash == HashService.hash_str(items[0].link)
    assert await parser.apply_hashes(await parser.items) == items
    assert [request[0] for request in requests] == ["GET", "POST", "POST"]
    headers, body = requests[1][2:]
    assert headers["Origin"] == base
    assert headers["Referer"] == base + path
    assert headers["X-Request-Context"] == "default"
    assert headers["Accept"] == "application/json, text/plain, */*"
    assert json.loads(body) == {
        "field_mask": ["id", "name"],
        "filter": [{"field": "channel_id", "is": "=", "value": "channel-id"}],
        "scope": ["public"],
        "page": 1,
        "per_page": 12,
        "sort": {"field": "published_at", "direction": "desc"},
    }
    assert parser.data["cache_storage_time"] == timedelta(days=1)


async def test_matreshka_reports_http_failure(api_server):
    base, routes, _ = api_server
    path = "/channel/channel-id/internal/videos"
    routes[path] = b"<title>Channel</title>"
    routes["/api/v2/video"] = (503, {"error": "Unavailable"})
    with pytest.raises(FeedUnavailable, match="http_request_failed"):
        await parser_for(MatreshkaFeed, base + path).items
