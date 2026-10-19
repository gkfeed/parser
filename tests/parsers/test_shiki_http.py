from collections import Counter
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from app.extensions.parsers.exceptions import FeedUnavailable
from app.parsers.shiki import ShikiFeed
from app.serializers.feed import Feed

pytestmark = pytest.mark.integration

VALID = b"""<html><h1>Spy x Family Season 2</h1><div class="b-menu-links">
<span class="entry"><span><time datetime="2023-12-23T21:32:47+03:00"></time>
</span><span>Episode 12</span></span>
<span class="entry"><span><time datetime="2023-12-16T21:32:47+03:00"></time>
</span><span>Episode 11</span></span></div></html>"""
CLOUDFLARE_ERROR = b"""<html><title>shikimori.one | 522: Connection timed out</title>
<div id="cf-error-details"><h1>Connection timed out</h1>Error code 522</div></html>"""
CHALLENGE = b'<html><form id="challenge-form">Verify browser</form></html>'
MALFORMED = b"<html><h1>Unexpected page</h1></html>"


@pytest.fixture
def shiki_server():
    requests = Counter()
    pages = {
        "/valid": (200, VALID),
        "/error": (522, CLOUDFLARE_ERROR),
        "/missing": (404, MALFORMED),
        "/blocked": (403, CHALLENGE),
        "/soft-error": (200, CLOUDFLARE_ERROR),
        "/challenge": (200, CHALLENGE),
        "/malformed": (200, MALFORMED),
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests[self.path] += 1
            status, body = pages[self.path]
            self.send_response(status)
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


@pytest.mark.parametrize("cached_html", [None, CLOUDFLARE_ERROR, CHALLENGE, MALFORMED])
async def test_shiki_refreshes_invalid_cache_and_parses_history(shiki_server, cached_html):
    base_url, requests = shiki_server
    url = base_url + "/valid"
    parser = ShikiFeed(Feed(id=1, title="Shiki", type="shiki", url=url), {})
    if cached_html is not None:
        parser.cache.set_with_expiry(url, cached_html, timedelta(minutes=5))

    items = await parser.items

    assert [item.text for item in items] == ["Episode 11", "Episode 12"]
    assert items[0].title == "Spy x Family Season 2 Episode 11"
    assert all(item.link == url for item in items)
    assert items[0].date < items[1].date
    assert parser.cache.get(url) == VALID
    assert requests["/valid"] == 1


@pytest.mark.parametrize(
    ("path", "exception", "reason"),
    [
        ("/error", FeedUnavailable, "http_request_failed"),
        ("/missing", FeedUnavailable, "http_request_failed"),
        ("/blocked", FeedUnavailable, "http_request_failed"),
        ("/soft-error", FeedUnavailable, "cloudflare_error"),
        ("/challenge", FeedUnavailable, "cloudflare_challenge"),
        ("/malformed", ValueError, "Shiki episode history"),
    ],
)
async def test_shiki_rejects_unusable_responses(shiki_server, path, exception, reason):
    base_url, requests = shiki_server
    url = base_url + path
    parser = ShikiFeed(Feed(id=1, title="Shiki", type="shiki", url=url), {})

    with pytest.raises(exception, match=reason):
        await parser.items

    assert not parser.cache.has_valid_cache(url)
    assert requests[path] == 1
