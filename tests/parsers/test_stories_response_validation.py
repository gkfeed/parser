import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

from app.extensions.parsers.exceptions import FeedUnavailable
from app.services.catbox import CatboxUploader
from app.services.media_upload import FallbackUploader
from app.services.tempfile import TempFileUploader

from .test_stories_loading import PAGE
from .test_stories_loading import stories_parser as stories_parser  # noqa: PLC0414 - export pytest fixture

pytestmark = pytest.mark.integration

MUTATIONS = {
    "missing_trigger": "trigger.remove()",
    "missing_active_tab": "result.firstChild.className = 'tabs-component__button'",
    "wrong_tab": "result.firstChild.textContent = 'Posts'",
    "missing_link": "list.querySelectorAll('a')[1].removeAttribute('href')",
    "invalid_url": "list.querySelectorAll('a')[1].href = 'data:text/plain,not-media'",
    "empty_list": (
        "list.querySelectorAll('.profile-media-list__item').forEach(card => card.remove())"
    ),
}


@pytest.fixture
def stories_server(monkeypatch):
    uploads = []
    failures = set()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state = parse_qs(urlsplit(self.path).query).get("state", [""])[0]
            mutation = MUTATIONS.get(state, "")
            # Change the response after the first media card was ready, while
            # pagination is settling, to exercise validation of the final HTML.
            body = PAGE.replace(
                b"  append();",
                f"  append(); setTimeout(() => {{ {mutation} }}, 500);".encode(),
            )
            self.respond(body, "text/html; charset=utf-8")

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            if self.path == "/catbox":
                source = parse_qs(body.decode())["url"][0]
                uploads.append(source)
                media_id = source.rsplit("/", 1)[-1]
                response = (
                    b"Upload failed"
                    if media_id in failures
                    else f"https://files.catbox.moe/{media_id}.jpg".encode()
                )
                self.respond(response, "text/plain")
                return
            source = json.loads(body)["url"]
            media_id = source.rsplit("/", 1)[-1]
            response = {"success": media_id not in failures, "file": {"id": media_id}}
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


@pytest.mark.parametrize(
    ("state", "reason"),
    [
        ("missing_trigger", "media_loading_unverified"),
        ("missing_active_tab", "media_response_invalid"),
        ("wrong_tab", "media_response_invalid"),
        ("missing_link", "media_response_invalid"),
        ("invalid_url", "media_response_invalid"),
        ("empty_list", "empty_unverified"),
    ],
)
async def test_stories_rejects_unverified_final_response(
    stories_server, stories_parser, state, reason
):
    _, uploads, _ = stories_server

    with pytest.raises(FeedUnavailable) as raised:
        await stories_parser(f"count=2&state={state}").items

    assert raised.value.reason == reason
    assert raised.value.retry_at is not None
    assert uploads == []


async def test_stories_retries_partial_upload_instead_of_returning_success(
    stories_server, stories_parser
):
    _, uploads, failures = stories_server
    failures.add("2")
    parser = stories_parser("count=2")

    with pytest.raises(FeedUnavailable) as raised:
        await parser.items

    assert raised.value.reason == "media_upload_error"
    assert raised.value.retry_at is not None
    assert len(uploads) == 2

    failures.clear()
    items = await parser.items

    assert {item.link for item in items} == {
        "https://files.catbox.moe/1.jpg",
        "https://files.catbox.moe/2.jpg",
    }
