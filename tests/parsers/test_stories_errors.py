from datetime import UTC, datetime, timedelta
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from app.extensions.parsers.exceptions import FeedUnavailable
from app.parsers.stories import InstagramStoriesFeed
from app.serializers.feed import Feed

pytestmark = pytest.mark.integration


@pytest.fixture
def stories_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = parse_qs(urlsplit(self.path).query)
            message = escape(query.get("message", [""])[0], quote=True)
            stage = escape(query.get("stage", [""])[0], quote=True)
            body = f"""<html><body data-message="{message}" data-stage="{stage}">
                <form class="search-form" onsubmit="search(); return false;">
                    <input class="search-form__input">
                    <button class="search-form__button">Search</button>
                </form>
                <div class="search-result"></div>
                <script>
                    const result = document.querySelector('.search-result');
                    function showError() {{
                        result.innerHTML = '<div class="error-message__text"></div>';
                        result.firstChild.textContent = document.body.dataset.message;
                    }}
                    function search() {{
                        if (document.body.dataset.stage === 'search') {{
                            showError();
                            return;
                        }}
                        result.innerHTML = '<button class="tabs-component__button" '
                            + 'onclick="showError()">Stories</button>';
                    }}
                </script>
                </body></html>""".encode()
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
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("stage", ["search", "stories"])
@pytest.mark.parametrize(
    ("message", "reason", "delay"),
    [
        ("No stories available", "empty_unverified", timedelta(minutes=1)),
        ("This account is private", "private", timedelta(days=1)),
        ("User not found", "not_found", timedelta(days=1)),
        ("Please try again later", "upstream_error", timedelta(minutes=1)),
    ],
)
async def test_stories_source_errors_are_unavailable(
    stories_server, stage, message, reason, delay
):
    feed = Feed(
        id=1, title="Stories", type="stories", url="https://www.instagram.com/example"
    )
    parser = InstagramStoriesFeed(feed, {})
    parser._service_url = (
        stories_server + "/?" + urlencode({"stage": stage, "message": message})
    )
    parser._selenium_wait_time = 0
    started = datetime.now(UTC)

    with pytest.raises(FeedUnavailable) as raised:
        await parser.items

    error = raised.value
    assert error.url == feed.url
    assert error.reason == reason
    assert error.retry_at is not None
    assert started + delay <= error.retry_at <= datetime.now(UTC) + delay
    assert not parser.cache.has_valid_cache(parser._service_url)
