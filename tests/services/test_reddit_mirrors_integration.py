import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from app.extensions.parsers.exceptions import FeedUnavailable
from app.parsers.reddit import RedditFeed
from app.serializers.feed import Feed
from app.services.http import HttpService
from app.services.redlib import RedlibClient
from app.services.url_ranker import URLRanker

pytestmark = pytest.mark.integration


@pytest.fixture
def mirror_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            pages = {
                "/instances.json": json.dumps(
                    {"instances": [{"url": "https://primary.example"}]}
                ).encode(),
                "/primary.example/r/neovim": b"<html><div id='error'></div></html>",
                "/red.artemislena.eu/r/neovim": (
                    b"<html><div class='stale_banner'>Old page</div>"
                    b"<div class='post'>Stale</div></html>"
                ),
                "/redlib.reallyaweso.me/r/neovim": (
                    b"<html><div class='post'>Fresh</div></html>"
                ),
            }
            body = pages.get(self.path, b"<html><div id='error'></div></html>")
            self.send_response(200)
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


@pytest.mark.parametrize(
    ("path", "expected"),
    [("neovim", b"Fresh"), ("missing", None)],
)
async def test_reddit_mirror_fallback(mirror_server, tmp_path, path, expected):
    feed = Feed(id=1, title="reddit", type="reddit", url=f"https://reddit.com/r/{path}")
    parser = RedditFeed(feed, {})

    async def fetch_mirror(url):
        return await parser.get_html(url.replace("https://", mirror_server + "/"))

    async def fetch_directory(url):
        return await HttpService.get(mirror_server + "/instances.json")

    client = RedlibClient(
        fetch_mirror,
        fetch_instances=fetch_directory,
        url_ranker=URLRanker(str(tmp_path / "ranks.json")),
    )
    if expected is None:
        with pytest.raises(FeedUnavailable, match="reddit_mirrors_exhausted"):
            await client.get_page_html(feed.url)
        return
    assert expected in await client.get_page_html(feed.url)
