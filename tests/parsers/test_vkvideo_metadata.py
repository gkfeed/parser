from collections import Counter
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from app.extensions.parsers.exceptions import FeedUnavailable
from app.parsers.vkvideo import VkVideoFeed
from app.serializers.feed import Feed
from app.services.hash import HashService
from app.utils.datetime import constant_datetime

PAGE = b"""<html><body>
<div data-testid="video_channel_name">Channel</div>
<div data-testid="catalog_item_video">
<div data-testid="video_card_title"><a href="/video-1_1">First video</a></div>
</div></body></html>"""


@pytest.fixture
def video_server():
    requests = Counter()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests[self.path] += 1
            entries = ""
            if self.path == "/unlinked.rss":
                entries = "<item><title>Video without a link</title></item>"
            if self.path == "/broken.rss":
                entries = f'<item><enclosure url="{base_url}/missing"/></item>'
            if self.path == "/videos.rss":
                entries = "".join(
                    f"<item><title>Video {index}</title>"
                    f'<enclosure url="{base_url}/-1_{index}.mp4"/>'
                    "<pubDate>Mon, 19 Oct 2026 12:00:00 GMT</pubDate></item>"
                    for index in range(1, 8)
                )
            body = (
                '<rss version="2.0"><channel><title>Channel</title>'
                f"{entries}</channel></rss>"
            ).encode()
            status = 404 if self.path == "/missing" else 200
            content_type = "application/rss+xml"
            if self.path.endswith(".mp4"):
                content_type, body = "video/mp4", b"fixture video"
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    base_url = f"http://127.0.0.1:{server.server_port}"
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield base_url, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def parser_for(url: str) -> VkVideoFeed:
    return VkVideoFeed(Feed(id=1, title="VK", type="vkvideo", url=url), {})


@pytest.mark.parametrize("path", ["/empty.rss", "/unlinked.rss", "/broken.rss"])
async def test_unusable_extraction_uses_cached_browser_page(video_server, path):
    base_url, requests = video_server
    parser = parser_for(base_url + path)
    parser.cache.set_with_expiry(parser.feed.url, PAGE, timedelta(hours=1))

    items = await parser.apply_hashes(await parser.items)

    assert len(items) == 1
    assert items[0].title == "VK Video: Channel"
    assert items[0].text == "First video"
    assert items[0].link == "https://vkvideo.ru/video-1_1"
    assert items[0].date == constant_datetime
    assert items[0].hash == HashService.hash_str(items[0].link)
    assert requests[path] == 1


async def test_unusable_extraction_and_page_raise_unavailable(video_server):
    base_url, _ = video_server
    parser = parser_for(base_url + "/empty.rss")
    parser.cache.set_with_expiry(parser.feed.url, b"<html></html>", timedelta(hours=1))

    with pytest.raises(FeedUnavailable, match="missing_content"):
        await parser.items


async def test_valid_extraction_preserves_limits_dates_links_and_cache(video_server):
    base_url, requests = video_server
    parser = parser_for(base_url + "/videos.rss")

    items = await parser.apply_hashes(await parser.items)
    request_counts = requests.copy()

    assert len(items) == 5
    assert [item.link for item in items] == [
        f"https://vkvideo.ru/video-1_{index}" for index in range(1, 6)
    ]
    assert [item.text for item in items] == [f"Video {index}" for index in range(1, 6)]
    assert all(item.title == "VK Video: Channel" for item in items)
    assert all(item.date == datetime(2026, 10, 19, 12, tzinfo=UTC) for item in items)
    assert all(item.hash == HashService.hash_str(item.link) for item in items)
    assert await parser.apply_hashes(await parser.items) == items
    assert requests == request_counts
