from collections import Counter
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from app.extensions.parsers.exceptions import FeedUnavailable
from app.parsers.shiki_ongoing import ShikiOngoingFeed
from app.serializers.feed import Feed
from app.utils.datetime import constant_datetime

pytestmark = pytest.mark.integration

PAGES = {
    "/empty": '<div class="fc-ongoings"></div>',
    "/populated": '''<div class="fc-ongoings">
        <article><a href="https://shikimori.one/animes/1">
            <span class="name-en">First anime</span></a>
            <meta itemprop="dateCreated" content="2026-10-19T12:00:00+03:00">
        </article>
        <article><a href="https://shikimori.one/animes/2">
            <span class="name-en">Second anime</span></a>
        </article>
    </div>''',
    "/unrelated": '<html><body><h1>Sign in</h1></body></html>',
    "/challenge": '<html><head><title>Just a moment...</title></head></html>',
    "/changed": '<div class="ongoings"><article></article></div>',
    "/blank": "",
}


@pytest.fixture
def shiki_server():
    requests = Counter()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests[self.path] += 1
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/unrelated")
                self.end_headers()
                return

            body = PAGES[self.path].encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def parser_for(url: str) -> ShikiOngoingFeed:
    return ShikiOngoingFeed(
        Feed(id=1, title="Ongoings", type="shiki:ongoing", url=url), {}
    )


async def test_shiki_accepts_empty_ongoings_container(shiki_server):
    base_url, requests = shiki_server
    parser = parser_for(base_url + "/empty")

    assert await parser.items == []
    assert await parser.items == []
    assert requests["/empty"] == 1


@pytest.mark.parametrize(
    "path", ["/unrelated", "/challenge", "/changed", "/blank", "/redirect"]
)
async def test_shiki_rejects_pages_without_ongoings_container(shiki_server, path):
    base_url, _ = shiki_server
    url = base_url + path
    parser = parser_for(url)

    for _ in range(2):
        with pytest.raises(FeedUnavailable, match="missing_ongoings_container") as exc:
            await parser.items
        assert exc.value.url == url
        assert exc.value.retry_at is None


async def test_shiki_preserves_items_and_hashes_from_cached_page(shiki_server):
    base_url, requests = shiki_server
    parser = parser_for(base_url + "/populated")

    items = await parser.apply_hashes(await parser.items)
    cached_items = await parser.apply_hashes(await parser.items)

    assert [item.title for item in items] == ["First anime", "Second anime"]
    assert [item.text for item in items] == ["First anime", "Second anime"]
    assert [item.link for item in items] == [
        "https://shikimori.one/animes/1",
        "https://shikimori.one/animes/2",
    ]
    assert [item.date for item in items] == [
        datetime.fromisoformat("2026-10-19T12:00:00+03:00"),
        constant_datetime,
    ]
    assert all(item.hash for item in items)
    assert items[0].hash != items[1].hash
    assert items == cached_items
    assert requests["/populated"] == 1
