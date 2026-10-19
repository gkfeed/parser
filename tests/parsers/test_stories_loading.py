import json
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.service import Service

from app.extensions.parsers.exceptions import FeedUnavailable
from app.parsers.stories import InstagramStoriesFeed
from app.serializers.feed import Feed
from app.services.catbox import CatboxUploader
from app.services.container import Container
from app.services.media_upload import FallbackUploader
from app.services.tempfile import TempFileUploader

pytestmark = pytest.mark.integration

# Anonyig's ProfileMediaList renders six cards at a time. Its 1px trigger
# reveals the next six on intersection, after a 200ms debounce.
PAGE = b"""<!doctype html><html><body>
<form class="search-form" onsubmit="search(); return false">
  <input class="search-form__input">
  <button class="search-form__button">Search</button>
</form>
<div class="search-result"></div>
<script>
const options = new URLSearchParams(location.search);
const result = document.querySelector('.search-result');
let shown = 0;
function search() {
  if (options.has('error')) {
    result.innerHTML = '<p class="error-message__text"></p>';
    result.firstChild.textContent = options.get('error');
    return;
  }
  result.innerHTML = '<button class="tabs-component__button" '
    + 'onclick="stories()">Stories</button>';
}
function stories() {
  result.firstChild.classList.add('tabs-component__button--active');
  const list = document.createElement('ul');
  list.className = 'profile-media-list';
  result.append(list);
  const trigger = document.createElement('div');
  trigger.className = 'trigger';
  trigger.style.height = '1px';
  list.append(trigger);
  function append() {
    const end = Math.min(shown + 6, Number(options.get('count')));
    while (shown < end) {
      const item = document.createElement('li');
      item.className = 'profile-media-list__item';
      item.style.height = '700px';
      item.innerHTML = '<a class="download-btn" href="'
        + location.origin + '/media/' + (++shown) + '">Download</a>';
      list.insertBefore(item, trigger);
    }
  }
  append();
  if (options.has('hidden')) result.style.display = 'none';
  new IntersectionObserver(([entry]) => {
    if (entry.isIntersecting) setTimeout(append, 200);
  }, {threshold: 0.5}).observe(trigger);
}
</script></body></html>"""


@pytest.fixture
def stories_server(monkeypatch):
    uploads = []
    failures = set()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.respond(PAGE, "text/html; charset=utf-8")

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            if self.path == "/catbox":
                source = parse_qs(body.decode())["url"][0]
                uploads.append(source)
                response = (
                    b"Upload failed"
                    if "catbox" in failures
                    else f"https://files.catbox.moe/{source.rsplit('/', 1)[-1]}.jpg".encode()
                )
                self.respond(response, "text/plain")
                return
            source = json.loads(body)["url"]
            response = {"success": False}
            if "tempfile" not in failures:
                response = {
                    "success": True,
                    "file": {"id": source.rsplit("/", 1)[-1]},
                }
            self.respond(json.dumps(response).encode(), "application/json")

        def respond(self, body, content_type):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    class LocalCatbox(CatboxUploader):
        host_url = base_url + "/catbox"

    class LocalTempFile(TempFileUploader):
        host_url = base_url + "/tempfile"

    monkeypatch.setattr(FallbackUploader, "uploaders", (LocalCatbox, LocalTempFile))
    try:
        yield base_url, uploads, failures
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.fixture
def stories_parser(stories_server):
    base_url, _, _ = stories_server

    def driver():
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1280,800")
        return webdriver.Chrome(
            service=Service("/usr/bin/chromedriver"), options=options
        )

    original = Container.get_data()
    Container.setup(replace(original, selenium_web_driver=driver))

    def parser_for(query):
        parser = InstagramStoriesFeed(
            Feed(
                id=1,
                title="Stories",
                type="stories",
                url="https://instagram.com/example",
            ),
            {},
        )
        parser._service_url = base_url + "/?" + query
        parser._selenium_wait_time = 0
        return parser

    try:
        yield parser_for
    finally:
        Container.setup(original)


@pytest.mark.parametrize("count", [7, 25])
async def test_stories_uploads_every_lazy_loaded_card(
    stories_server, stories_parser, count
):
    _, uploads, _ = stories_server

    items = await stories_parser(f"count={count}").items

    assert len(items) == count
    assert {urlsplit(url).path for url in uploads} == {
        f"/media/{number}" for number in range(1, count + 1)
    }


@pytest.mark.parametrize(
    ("message", "reason"),
    [
        ("No+stories+found", "empty_unverified"),
        ("Something+went+wrong", "upstream_error"),
    ],
)
async def test_stories_rejects_source_errors(
    stories_server, stories_parser, message, reason
):
    _, uploads, _ = stories_server

    with pytest.raises(FeedUnavailable) as raised:
        await stories_parser(f"error={message}").items

    assert raised.value.reason == reason
    assert raised.value.retry_at is not None
    assert uploads == []


async def test_stories_uses_fallback_after_catbox_error(stories_server, stories_parser):
    _, _, failures = stories_server
    failures.add("catbox")

    items = await stories_parser("count=1").items

    assert len(items) == 1
    assert items[0].link == "https://tempfile.org/1/download"


async def test_stories_rejects_failed_uploads(stories_server, stories_parser):
    _, _, failures = stories_server
    failures.update(("catbox", "tempfile"))

    with pytest.raises(FeedUnavailable) as raised:
        await stories_parser("count=1").items

    assert raised.value.reason == "media_upload_error"


async def test_stories_rejects_hidden_pagination(stories_server, stories_parser):
    _, uploads, _ = stories_server

    with pytest.raises(FeedUnavailable) as raised:
        await stories_parser("count=7&hidden=1").items

    assert raised.value.reason == "media_loading_unverified"
    assert uploads == []


async def test_stories_rejects_partial_list_at_loading_deadline(
    stories_server, stories_parser
):
    _, uploads, _ = stories_server
    parser = stories_parser("count=1000")
    parser._results_wait_time = 1

    with pytest.raises(FeedUnavailable) as raised:
        await parser.items

    assert raised.value.reason == "media_loading_timeout"
    assert uploads == []
