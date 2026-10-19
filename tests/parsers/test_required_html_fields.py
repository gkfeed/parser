from collections import Counter
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from app.extensions.parsers.exceptions import FeedUnavailable
from app.parsers.author_today import AuthorTodayFeed
from app.parsers.insolarance import InsolaranceFeed
from app.parsers.porno365 import Porno365Feed
from app.serializers.feed import Feed, Item
from app.utils.datetime import constant_datetime


def chapters(content: str) -> str:
    return f'<div id="tab-chapters"><ul class="table-of-content">{content}</ul></div>'


def videos(content: str) -> str:
    return f'<ul class="videos_ul">{content}</ul>'


AUTHOR_CHAPTER = '''<li><a href="/reader/42/1"><b> First </b><i> second </i></a>
<span class="chapter-publish-time"><time data-time="2026-10-19T12:30:00+03:00">
</time></span></li>'''
INSOLARANCE_POST = '''<article><a href="/ignore">Ignore</a>
<a href="/post/42"><b> First </b><i> second </i></a><a>Footer</a></article>'''
VIDEO = '''<li class="video_block"><a class="image" href="/movie/42?view=full#part">
<img alt="Fallback title"></a><p><b> First </b><i> second </i></p></li>'''


@pytest.fixture(scope="module")
def html_server():
    pages: dict[str, str | None] = {}
    requests = Counter()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests[self.path] += 1
            page = pages[self.path]
            if page is None:
                self.close_connection = True
                return
            body = page.encode()
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
        yield f"http://127.0.0.1:{server.server_port}", pages, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def parser_for(parser_type, url: str):
    return parser_type(Feed(id=1, title="HTML feed", type="html", url=url), {})


@pytest.mark.parametrize(
    ("parser_type", "html", "title", "link", "date"),
    [
        (
            AuthorTodayFeed,
            chapters(AUTHOR_CHAPTER),
            "First second",
            "https://author.today/reader/42/1",
            datetime.fromisoformat("2026-10-19T12:30:00+03:00"),
        ),
        (InsolaranceFeed, INSOLARANCE_POST, "First  second", "/post/42", constant_datetime),
        (
            Porno365Feed,
            videos(VIDEO),
            "First  second",
            "http://porno365.broker/movie/42?view=full#part",
            constant_datetime,
        ),
        (
            Porno365Feed,
            videos('''<li class="video_block"><a class="image"
            href="https://old.example/movie/42?view=full#part">
            <img alt="  Fallback  title  "></a></li>'''),
            "Fallback  title",
            "http://porno365.broker/movie/42?view=full#part",
            constant_datetime,
        ),
    ],
)
async def test_html_parsers_preserve_item_fields(
    html_server, parser_type, html, title, link, date
):
    base_url, pages, requests = html_server
    pages["/feed"] = html
    parser = parser_for(parser_type, base_url + "/feed")
    before = requests["/feed"]

    items = await parser.items

    assert items == [Item(title=title, text=title, link=link, date=date)]
    assert await parser.items == items
    assert requests["/feed"] == before + 1
    hashed_items = await parser.apply_hashes(items)
    assert hashed_items[0].hash
    assert await parser.apply_hashes(await parser.items) == hashed_items


@pytest.mark.parametrize(
    ("parser_type", "html", "field"),
    [
        (AuthorTodayFeed, chapters("<li></li>"), "chapter link"),
        (
            AuthorTodayFeed,
            chapters(AUTHOR_CHAPTER.replace("<b> First </b><i> second </i>", " ")),
            "chapter title",
        ),
        (
            AuthorTodayFeed,
            chapters('<li><a href="/reader/42/1">Title</a></li>'),
            "chapter publication time",
        ),
        (
            AuthorTodayFeed,
            chapters(AUTHOR_CHAPTER.replace("data-time=", "other=")),
            "chapter publication time",
        ),
        (
            AuthorTodayFeed,
            chapters(AUTHOR_CHAPTER.replace("2026-10-19T12:30:00+03:00", "invalid")),
            "chapter publication time",
        ),
        (InsolaranceFeed, "<article><a>Footer</a></article>", "post title"),
        (
            InsolaranceFeed,
            '<article><a>Title</a><a href="/footer">Footer</a></article>',
            "post link",
        ),
        (Porno365Feed, "<html></html>", "video list"),
        (Porno365Feed, videos('<li class="video_block"></li>'), "post title"),
        (Porno365Feed, videos('<li class="video_block"><img></li>'), "alt.*post title"),
        (
            Porno365Feed,
            videos('<li class="video_block"><p>Title</p></li>'),
            "post link",
        ),
        (Porno365Feed, videos(VIDEO.replace("href=", "other=")), "href.*post link"),
    ],
)
async def test_html_parsers_report_required_field(html_server, parser_type, html, field):
    base_url, pages, _ = html_server
    pages["/malformed"] = html
    parser = parser_for(parser_type, base_url + "/malformed")

    with pytest.raises(ValueError, match=field):
        await parser.items


@pytest.mark.parametrize(
    ("parser_type", "html"),
    [
        (AuthorTodayFeed, chapters("")),
        (InsolaranceFeed, "<main>No posts yet</main>"),
        (Porno365Feed, videos("")),
    ],
)
async def test_html_parsers_accept_empty_lists(html_server, parser_type, html):
    base_url, pages, _ = html_server
    pages["/empty"] = html

    assert await parser_for(parser_type, base_url + "/empty").items == []


@pytest.mark.parametrize(
    ("parser_type", "html"),
    [
        (AuthorTodayFeed, chapters(AUTHOR_CHAPTER)),
        (InsolaranceFeed, INSOLARANCE_POST),
        (Porno365Feed, videos(VIDEO)),
    ],
)
async def test_html_parsers_propagate_unavailability_and_recover(
    html_server, parser_type, html
):
    base_url, pages, _ = html_server
    pages["/unavailable"] = None
    parser = parser_for(parser_type, base_url + "/unavailable")

    with pytest.raises(FeedUnavailable, match="http_request_failed"):
        await parser.items

    pages["/unavailable"] = html
    assert len(await parser.items) == 1
