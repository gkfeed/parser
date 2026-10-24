from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from structlog.testing import capture_logs

from app.extensions.parsers.exceptions import FeedUnavailable
from app.parsers.web import WebFeed
from app.serializers.feed import Feed

pytestmark = pytest.mark.integration

VALID_RSS = (
    b"<rss version='2.0'><channel><item><title>Post</title>"
    b"<link>https://example.com/post</link><description>Text</description>"
    b"<pubDate>Thu, 22 Oct 2026 08:00:00 GMT</pubDate>"
    b"<guid>post-1</guid></item></channel></rss>"
)
PAGES = {
    "/valid": VALID_RSS,
    "/utf16": VALID_RSS.decode().encode("utf-16"),
    "/empty": b"<rss version='2.0'><channel /></rss>",
    "/html": b"<!DOCTYPE html><html><head><meta name='private-body'></head></html>",
    "/xhtml": b"<html xmlns='http://www.w3.org/1999/xhtml'><body /></html>",
    "/html-utf16": "<HTML><body><br></body></HTML>".encode("utf-16"),
    "/xml": b"<rss><channel>\n</rss>",
    "/encoding": b"<?xml version='1.0' encoding='private-encoding'?><rss />",
    "/incorrect-encoding": b"<?xml version='1.0' encoding='utf-16'?><rss />",
    "/nonrss": b"<feed xmlns='http://www.w3.org/2005/Atom' />",
    "/no-channel": b"<rss />",
    "/multiple-channels": b"<rss><channel /><channel /></rss>",
    "/truncated": b"<rss><channel>",
    "/empty-body": b"",
    "/missing-title": VALID_RSS.replace(b"<title>Post</title>", b"<title />"),
    "/invalid-date": VALID_RSS.replace(b"Thu, 22 Oct 2026 08:00:00 GMT", b"invalid"),
}


@pytest.fixture(scope="module")
def rss_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = PAGES[self.path.split("?", 1)[0]]
            self.send_response(200)
            # HTML must still be rejected when the server labels it as RSS.
            self.send_header("Content-Type", "application/rss+xml")
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


def web_feed(url: str) -> WebFeed:
    return WebFeed(Feed(id=89, title="RSS", type="web", url=url), {})


@pytest.mark.parametrize("path", ["/valid", "/utf16"])
async def test_valid_rss_preserves_items_and_hashes(rss_server, path):
    parser = web_feed(rss_server + path)
    items = await parser.apply_hashes(await parser.items)

    assert len(items) == 1
    assert items[0].title == "Post"
    assert items[0].link == "https://example.com/post"
    assert items[0].text == "Text"
    assert items[0].guid == "post-1"
    assert items[0].date.isoformat() == "2026-10-22T08:00:00+00:00"
    assert items[0].hash


async def test_explicit_empty_rss_channel_is_accepted(rss_server):
    assert await web_feed(rss_server + "/empty").items == []


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        ("/html", "rss_html_response"),
        ("/xhtml", "rss_html_response"),
        ("/html-utf16", "rss_html_response"),
        ("/xml", "rss_invalid_xml"),
        ("/encoding", "rss_invalid_encoding"),
        ("/incorrect-encoding", "rss_invalid_encoding"),
        ("/nonrss", "rss_invalid_document"),
        ("/no-channel", "rss_invalid_document"),
        ("/multiple-channels", "rss_invalid_document"),
        ("/truncated", "rss_invalid_xml"),
        ("/empty-body", "rss_invalid_xml"),
    ],
)
async def test_unusable_rss_raises_and_logs_safe_diagnostics(rss_server, path, reason):
    url = rss_server.replace("://", "://private-user:private-password@")
    url += path + "?token=private-query#private-fragment"

    with capture_logs() as events, pytest.raises(FeedUnavailable) as raised:
        await web_feed(url).items

    assert raised.value.reason == reason
    assert raised.value.url == rss_server + path
    assert raised.value.__cause__ is not None
    event = next(event for event in events if event["event"] == "rss_parse_failed")
    assert event["url"] == rss_server + path
    assert event["reason"] == reason
    assert event["response_bytes"] == len(PAGES[path])
    assert "private-" not in str(events) + str(raised.value)
    if path == "/xml":
        assert event["xml_error"] == "mismatched tag"
        assert event["xml_error_code"] == 7
        assert event["xml_line"] == 2
        assert event["xml_column"] == 2


@pytest.mark.parametrize("path", ["/missing-title", "/invalid-date"])
async def test_invalid_rss_items_still_raise(rss_server, path):
    with pytest.raises(ValueError):
        await web_feed(rss_server + path).items
