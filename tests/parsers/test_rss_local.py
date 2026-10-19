from collections import Counter
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from app.extensions.parsers.exceptions import FeedUnavailable
from app.parsers.sasflix import SasflixFeed
from app.parsers.web import WebFeed
from app.serializers.feed import Feed

pytestmark = pytest.mark.integration

ITEM = """<item><title>Post</title><link>/post</link>
<pubDate>Mon, 14 Sep 2026 10:00:00 +0300</pubDate><guid>post-1</guid>
{content}</item>"""


def rss(*items: str) -> bytes:
    return (
        '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">'
        "<channel><title>Feed</title><link>https://example.com</link>"
        "<description>Posts</description>" + "".join(items) + "</channel></rss>"
    ).encode()


@pytest.fixture
def rss_server():
    responses: dict[str, tuple[int, bytes]] = {}
    requests = Counter()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests[self.path] += 1
            status, body = responses.get(self.path, (404, b"Not found"))
            self.send_response(status)
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
        yield f"http://127.0.0.1:{server.server_port}", responses, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def parser_for(parser_type, url):
    return parser_type(Feed(id=1, title="RSS", type="web", url=url), {})


@pytest.mark.parametrize(
    ("content", "web_text", "sasflix_text"),
    [
        (
            (
                "<description><![CDATA[<p>Кратко & ясно</p>]]></description>"
                "<content:encoded><![CDATA[<p>Полностью</p>]]></content:encoded>"
                '<enclosure url="https://example.com/cover.jpg" />'
            ),
            "<p>Кратко & ясно</p>",
            "<p>Полностью</p>",
        ),
        (
            (
                "<description>&lt;p&gt;Summary&lt;/p&gt;</description>"
                '<enclosure url="https://example.com/cover.jpg" />'
            ),
            "<p>Summary</p>",
            '<img src="https://example.com/cover.jpg" alt="" />',
        ),
        (
            "<encoded><![CDATA[<p>Full post</p>]]></encoded>",
            "<p>Full post</p>",
            "<p>Full post</p>",
        ),
        (
            (
                "<content:encoded />"
                '<enclosure url="https://example.com/cover.jpg?a=1&amp;b=2" />'
            ),
            '<img src="https://example.com/cover.jpg?a=1&amp;b=2" alt="" />',
            '<img src="https://example.com/cover.jpg?a=1&amp;b=2" alt="" />',
        ),
        (
            '<description>Summary</description><enclosure url="" />',
            "Summary",
            "Summary",
        ),
        ("", "", ""),
    ],
)
async def test_rss_content_dates_guid_and_hashes(
    rss_server, content, web_text, sasflix_text
):
    base_url, responses, _ = rss_server
    responses["/rss.xml"] = (200, rss(ITEM.format(content=content)))
    web = parser_for(WebFeed, base_url + "/rss.xml")
    sasflix = parser_for(SasflixFeed, base_url)

    web_items = await web.apply_hashes(await web.items)
    sasflix_items = await sasflix.apply_hashes(await sasflix.items)

    assert len(web_items) == len(sasflix_items) == 1
    web_item, sasflix_item = web_items[0], sasflix_items[0]
    for item in (web_item, sasflix_item):
        assert item.title == "Post"
        assert item.link == "/post"
        assert item.date.isoformat() == "2026-09-14T07:00:00+00:00"
    assert web_item.text == web_text
    assert sasflix_item.text == sasflix_text
    assert web_item.guid == "post-1"
    assert sasflix_item.guid is None
    assert web_item.hash == sha256(b"post-1").hexdigest()
    assert sasflix_item.hash == sha256(b"/post").hexdigest()


@pytest.mark.parametrize("suffix", ["", "/", "/rss.xml", "/rss.xml/"])
async def test_sasflix_normalizes_and_caches_rss(rss_server, suffix):
    base_url, responses, requests = rss_server
    responses["/news/rss.xml"] = (200, rss(ITEM.format(content="")))
    parser = parser_for(SasflixFeed, base_url + "/news" + suffix)

    first = await parser.items
    responses["/news/rss.xml"] = (503, b"Unavailable")
    second = await parser_for(SasflixFeed, base_url + "/news" + suffix).items

    assert first == second
    assert requests == {"/news/rss.xml": 1}


@pytest.mark.parametrize("parser_type", [WebFeed, SasflixFeed])
async def test_valid_empty_rss(rss_server, parser_type):
    base_url, responses, _ = rss_server
    responses["/rss.xml"] = (200, rss())

    assert await parser_for(parser_type, base_url + "/rss.xml").items == []


@pytest.mark.parametrize("parser_type", [WebFeed, SasflixFeed])
@pytest.mark.parametrize(
    ("body", "reason"),
    [
        (b"", "Invalid RSS XML"),
        (
            b'<?xml version="1.0" encoding="unknown-encoding"?><rss><channel /></rss>',
            "Invalid RSS XML",
        ),
        (b"<rss><channel><item>", "Invalid RSS XML"),
        (b"<html><body>Blocked</body></html>", "Expected an RSS document"),
        (b"<feed><entry /></feed>", "Expected an RSS document"),
        (b"<rss />", "Expected an RSS document"),
        (b"<rss><channel /><channel /></rss>", "Expected an RSS document"),
        (rss(ITEM.format(content="").replace("<link>/post</link>", "")), "link"),
        (
            rss(ITEM.format(content="").replace("<title>Post</title>", "<title />")),
            "title",
        ),
        (
            rss(ITEM.format(content="").replace("Mon, 14 Sep 2026 10:00:00 +0300", "")),
            "pub_date",
        ),
        (
            rss(
                ITEM.format(content="").replace(
                    "Mon, 14 Sep 2026 10:00:00 +0300", "not a date"
                )
            ),
            "invalid pubDate",
        ),
        (
            rss(
                ITEM.format(content="").replace(
                    "Mon, 14 Sep 2026 10:00:00 +0300", "31 Feb 2026"
                )
            ),
            "invalid pubDate",
        ),
    ],
)
async def test_invalid_rss_is_an_error(rss_server, parser_type, body, reason):
    base_url, responses, _ = rss_server
    responses["/rss.xml"] = (200, body)

    with pytest.raises(ValueError, match=reason):
        await parser_for(parser_type, base_url + "/rss.xml").items


@pytest.mark.parametrize("parser_type", [WebFeed, SasflixFeed])
@pytest.mark.parametrize("status", [403, 404, 429, 503])
async def test_http_failure_is_unavailable_and_can_recover(
    rss_server, parser_type, status
):
    base_url, responses, requests = rss_server
    responses["/rss.xml"] = (status, rss())
    parser = parser_for(parser_type, base_url + "/rss.xml")

    with pytest.raises(FeedUnavailable, match=f"http_status_{status}"):
        await parser.items

    responses["/rss.xml"] = (200, rss(ITEM.format(content="")))
    assert len(await parser.items) == 1
    assert requests["/rss.xml"] == 2


@pytest.mark.parametrize("parser_type", [WebFeed, SasflixFeed])
async def test_connection_failure_is_unavailable(rss_server, parser_type):
    base_url, _, _ = rss_server
    # The server only listens on IPv4, so this real connection is refused.
    url = base_url.replace("127.0.0.1", "[::1]") + "/rss.xml"

    with pytest.raises(FeedUnavailable, match="http_request_failed") as error:
        await parser_for(parser_type, url).items

    assert error.value.__cause__ is not None


async def test_web_hash_without_guid_and_sasflix_missing_title(rss_server):
    base_url, responses, _ = rss_server
    responses["/rss.xml"] = (
        200,
        rss(
            ITEM.format(content="<description>Summary</description>").replace(
                "<guid>post-1</guid>", ""
            )
        ),
    )
    parser = parser_for(WebFeed, base_url + "/rss.xml")
    items = await parser.apply_hashes(await parser.items)
    assert items[0].guid == ""
    assert items[0].hash == sha256(b"PostSummary").hexdigest()

    responses["/rss.xml"] = (
        200,
        rss(ITEM.format(content="").replace("<title>Post</title>", "")),
    )
    with pytest.raises(ValueError, match="title"):
        await parser_for(WebFeed, base_url + "/rss.xml").items
    items = await parser_for(SasflixFeed, base_url).items
    assert items[0].title == "No Title"
