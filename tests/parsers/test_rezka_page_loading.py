from collections import Counter
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from app.extensions.parsers.exceptions import UnavailableFeed
from app.parsers.rezka import RezkaFeed
from app.serializers.feed import Feed
from app.services.selenium import SeleniumGetHtmlArgs, SeleniumService

pytestmark = pytest.mark.integration

CARD = b'<html><body><h1>Series</h1><p>No episodes yet</p></body></html>'
ACCESS_DENIED = '''<html><head><title>Ошибка доступа (403)</title></head>
<body><div class="content"><div class="error-code">ОШИБКА ДОСТУПА
<div>403</div></div></div></body></html>'''.encode()


@pytest.fixture
def rezka_server():
    requests = Counter()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests[self.path] += 1
            if self.path == "/blocked.html":
                status, body = 403, ACCESS_DENIED
            elif self.path == "/failed.html" or (
                self.path == "/recover.html" and requests[self.path] == 1
            ):
                status, body = 500, b""
            else:
                status, body = 200, CARD
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


def parser_for(url: str) -> RezkaFeed:
    return RezkaFeed(Feed(id=1, title="Rezka", type="rezka", url=url), {})


async def test_rezka_recovers_and_caches_normal_card_without_episodes(rezka_server):
    base_url, requests = rezka_server
    url = base_url + "/recover.html"
    parser = parser_for(url)

    html = await parser.get_html(url)

    assert b"No episodes yet" in html
    assert requests["/recover.html"] == 2
    assert await parser.get_html(url) == html
    assert requests["/recover.html"] == 2


@pytest.mark.parametrize(
    ("path", "reason", "attempts"),
    [("/failed.html", "HTTP ERROR 500", 3), ("/blocked.html", "403", 1)],
)
async def test_rezka_rejects_error_pages_without_caching(
    rezka_server, path, reason, attempts
):
    base_url, requests = rezka_server
    url = base_url + path
    parser = parser_for(url)

    with pytest.raises(UnavailableFeed, match=reason):
        await parser.get_html(url)

    assert requests[path] == attempts
    assert not parser.cache.has_valid_cache(url)


async def test_rezka_discards_previously_cached_browser_error(rezka_server):
    base_url, requests = rezka_server
    url = base_url + "/recover.html"
    error_html = await SeleniumService.get_html(
        SeleniumGetHtmlArgs(
            url=url,
            should_delete_cookies=False,
            should_load_cookies=False,
            should_save_cookies=False,
            make_actions_function=None,
            selenium_wait_timeout_seconds=0,
        )
    )
    assert "HTTP ERROR 500" in error_html
    parser = parser_for(url)
    parser.cache.set_with_expiry(url, error_html.encode(), timedelta(hours=1))

    html = await parser.get_html(url)

    assert b"No episodes yet" in html
    assert requests["/recover.html"] == 2
    assert parser.cache.get(url) == html
