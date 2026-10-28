import json
from collections import Counter
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from app.parsers.anilibria import AnilibriaFeed
from app.parsers.mangalib import MangaLibFeed
from app.parsers.sasflix import SasflixFeed
from app.serializers.feed import Feed
from app.services.anilibria import AnilibriaClient
from app.services.mangalib import MangaLibClient
from app.services.rss import RSSParseError

pytestmark = pytest.mark.integration

RSS = (
    b"<rss version='2.0'><channel><item><title>Post</title>"
    b"<link>https://example.com/post</link><description>Text</description>"
    b"<encoded>Full text</encoded><enclosure url='https://example.com/image' />"
    b"<pubDate>Thu, 22 Oct 2026 08:00:00 GMT</pubDate>"
    b"<guid>post-1</guid></item></channel></rss>"
)
CHAPTERS = json.dumps(
    {
        "data": [
            {
                "volume": "1",
                "number": "2",
                "name": "Chapter",
                "branches": [{"created_at": "2026-10-22T08:00:00+00:00"}],
            }
        ]
    }
).encode()
RELEASE = json.dumps(
    {
        "name": {"main": "Show"},
        "episodes": [
            {
                "id": "episode-1",
                "ordinal": 1,
                "name": "Episode",
                "preview": {"src": "/image.jpg"},
            }
        ],
    }
).encode()
HTML_ERROR = b"<html>Temporary error</html>"


@pytest.fixture(params=["sasflix", "mangalib", "anilibria"])
def source(request, monkeypatch):
    requests = Counter()
    headers = {}
    pages = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests[self.path] += 1
            headers[self.path] = dict(self.headers)
            responses = pages[self.path]
            body = responses[min(requests[self.path] - 1, len(responses) - 1)]
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    # Configure API addresses only; requests, parsing and cache remain real.
    monkeypatch.setattr(MangaLibClient, "_api_base_url", base + "/manga/")
    monkeypatch.setattr(
        AnilibriaClient, "_api_base_urls", tuple(base + f"/{i}/" for i in range(3))
    )
    configs = {
        "sasflix": (SasflixFeed, "/", ["/rss.xml"], RSS, b"<rss><channel /></rss>"),
        "mangalib": (
            MangaLibFeed,
            "/ru/manga/slug",
            ["/manga/slug/chapters"],
            CHAPTERS,
            b'{"data": []}',
        ),
        "anilibria": (
            AnilibriaFeed,
            "/release/slug",
            [f"/{i}/anime/releases/slug" for i in range(3)],
            RELEASE,
            b'{"name": {"main": "Show"}, "episodes": []}',
        ),
    }
    parser_type, path, routes, valid, empty = configs[request.param]
    parser = parser_type(
        Feed(id=1, title="Source", type=request.param, url=base + path), {}
    )
    for route in routes:
        pages[route] = [valid]
    try:
        yield parser, base, routes, valid, empty, pages, requests, headers
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("legacy_cache", [False, True])
@pytest.mark.parametrize("failure", ["html", "invalid_item"])
async def test_failed_response_recovers_and_valid_cache_is_reused(
    source, legacy_cache, failure
):
    parser, base, routes, valid, _, pages, requests, headers = source
    invalid_item = {
        "sasflix": RSS.replace(b"Thu, 22 Oct 2026 08:00:00 GMT", b"invalid"),
        "mangalib": CHAPTERS.replace(b"2026-10-22T08:00:00+00:00", b"invalid"),
        "anilibria": RELEASE.replace(b'"src": "/image.jpg"', b'"src": ""'),
    }
    invalid = HTML_ERROR if failure == "html" else invalid_item[parser.feed.type]
    for route in routes:
        pages[route] = [invalid, valid]
        if legacy_cache:
            parser.cache.set_with_expiry(base + route, invalid, timedelta(hours=1))

    expected_error = (
        RSSParseError if parser.feed.type == "sasflix" and failure == "html" else ValueError
    )
    with pytest.raises(expected_error):
        await parser.items

    assert all(requests[route] == 1 for route in routes)
    assert all(not parser.cache.has_valid_cache(base + route) for route in routes)

    # A new parser instance models the next scheduled run with the same cache.
    recovered = type(parser)(parser.feed, {})
    items = await recovered.apply_hashes(await recovered.items)
    assert len(items) == 1
    assert items[0].title and items[0].text and items[0].date and items[0].link
    assert items[0].hash
    if parser.feed.type == "sasflix":
        assert items[0].text == "Full text"
        assert items[0].guid is None
    if parser.feed.type == "mangalib":
        assert headers[routes[0]]["Site-Id"] == "1"
        assert headers[routes[0]]["Accept"] == "application/json"
        assert headers[routes[0]]["Referer"] == "https://mangalib.org/"

    url = base + routes[0]
    expiry = parser.cache.get_expiry(url)
    snapshot = requests.copy()
    assert parser.cache.get(url) == valid
    assert await recovered.apply_hashes(await recovered.items) == items
    assert requests == snapshot
    assert parser.cache.get_expiry(url) == expiry


async def test_confirmed_empty_payload_is_cached(source):
    parser, base, routes, _, empty, pages, requests, _ = source
    for route in routes:
        pages[route] = [empty]

    assert await parser.items == []
    assert await type(parser)(parser.feed, {}).items == []
    assert requests == {routes[0]: 1}
    assert parser.cache.get(base + routes[0]) == empty


@pytest.mark.parametrize("source", ["anilibria"], indirect=True)
async def test_anilibria_recovers_primary_mirror_before_reusing_fallback(source):
    parser, base, routes, valid, _, pages, requests, _ = source
    pages[routes[0]] = [HTML_ERROR, valid]

    first = await parser.apply_hashes(await parser.items)
    assert len(first) == 1
    assert requests == {routes[0]: 1, routes[1]: 1}
    assert not parser.cache.has_valid_cache(base + routes[0])
    assert parser.cache.get(base + routes[1]) == valid

    assert await parser.apply_hashes(await parser.items) == first
    assert requests == {routes[0]: 2, routes[1]: 1}
    assert await parser.apply_hashes(await parser.items) == first
    assert requests == {routes[0]: 2, routes[1]: 1}
