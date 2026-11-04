from collections import Counter
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from app.extensions.parsers.exceptions import FeedUnavailable
from app.parsers.hltv import HltvFeed
from app.parsers.rezka import RezkaFeed
from app.serializers.feed import Feed

pytestmark = pytest.mark.integration

VALID = b"<html><h2 class='standard-headline'>Upcoming matches for Team</h2></html>"
HLTV_CHALLENGE = b"<html><title>Just a moment...</title></html>"
ANUBIS_CHALLENGE = b"<html><div id='anubis_challenge'>Verify browser</div></html>"
TRANSIENT_ERROR = (
    b"<html><body class='neterror'><div class='error-code'>"
    b"net::ERR_CONNECTION_RESET</div></body></html>"
)


@pytest.fixture
def page_server():
    requests = Counter()
    pages = {"/anubis": ANUBIS_CHALLENGE, "/transient": TRANSIENT_ERROR}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests[self.path] += 1
            body = pages.get(self.path, VALID)
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


@pytest.mark.parametrize(
    ("parser_type", "feed_type", "cached_html"),
    [
        (HltvFeed, "hltv", HLTV_CHALLENGE),
        (HltvFeed, "hltv", b"<html><form id='challenge-form'></form></html>"),
        (RezkaFeed, "rezka", ANUBIS_CHALLENGE),
    ],
)
async def test_invalid_cached_page_is_replaced_and_valid_page_reused(
    page_server, parser_type, feed_type, cached_html
):
    base_url, requests = page_server
    url = base_url + "/valid"
    parser = parser_type(Feed(id=1, title="Page", type=feed_type, url=url), {})
    parser.cache.set_with_expiry(url, cached_html, timedelta(hours=1))

    html = await parser.get_html(url)

    assert b"Upcoming matches for Team" in html
    assert parser.cache.get(url) == html
    assert await parser.get_html(url) == html
    assert requests["/valid"] == 1


@pytest.mark.parametrize(
    ("path", "reason", "attempts", "expected_requests"),
    [
        ("/anubis", "Anubis browser challenge", 3, 1),
        ("/transient", "net::ERR_CONNECTION_RESET", 1, 1),
        ("/transient", "net::ERR_CONNECTION_RESET", 3, 3),
    ],
)
async def test_rezka_retries_only_transient_pages_without_caching(
    page_server, path, reason, attempts, expected_requests
):
    base_url, requests = page_server
    url = base_url + path
    parser = RezkaFeed(Feed(id=1, title="Page", type="rezka", url=url), {})
    parser.cache.set_with_expiry(url, ANUBIS_CHALLENGE, timedelta(hours=1))

    with pytest.raises(FeedUnavailable) as raised:
        await parser.get_html(url, attempts=attempts)

    assert raised.value.url == url
    assert raised.value.reason == reason
    assert requests[path] == expected_requests
    assert not parser.cache.has_valid_cache(url)
