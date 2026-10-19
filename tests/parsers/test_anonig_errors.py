import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from threading import Thread
from urllib.parse import urlsplit

import pytest
from PIL import Image

from app.extensions.parsers.exceptions import FeedUnavailable
from app.parsers.instagram import AnonyigInstagramFeed
from app.serializers.feed import Feed
from app.services.hash import HashService

pytestmark = pytest.mark.integration


@pytest.fixture
def anonyig_server():
    image = BytesIO()
    Image.new("RGB", (2, 2), "red").save(image, format="PNG")
    image_bytes = image.getvalue()
    encoded = base64.b64encode(image_bytes).decode()
    pages = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/image.png":
                self.respond(200, image_bytes, "image/png")
                return
            if path == "/failed.png":
                self.respond(503, b"unavailable", "text/plain")
                return
            if path == "/broken.png":
                self.respond(200, b"not an image", "image/png")
                return
            if path == "/disconnect.png":
                self.close_connection = True
                return
            if path not in pages:
                self.respond(404, b"not found", "text/plain")
                return
            body = (
                '<html><body><form class="search-form">'
                '<input class="search-form__input">'
                '<button type="button" class="search-form__button">Search</button>'
                '</form><div class="search-result">'
                + pages[path]
                + "</div></body></html>"
            ).encode()
            self.respond(200, body, "text/html; charset=utf-8")

        def respond(self, status, body, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", pages, encoded
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def parser_for(base_url, pages, content):
    pages["/posts"] = content
    parser = AnonyigInstagramFeed(
        Feed(id=1, title="Instagram", type="inst", url="https://instagram.com/example"),
        {},
    )
    parser._service_url = base_url + "/posts"
    return parser


def media(content):
    return f'<div class="profile-media-list__item">{content}</div>'


@pytest.mark.parametrize("source", ["remote", "inline"])
async def test_anonyig_images_preserve_items_and_hashes(anonyig_server, source):
    base_url, pages, encoded = anonyig_server
    src = (
        base_url + "/image.png?signature=secret"
        if source == "remote"
        else "data:image/png;base64," + encoded
    )
    video = media(
        '<span class="tags__item--video"></span>'
        '<a href="https://media.example/video.mp4?signature=secret">Video</a>'
    )
    parser = parser_for(base_url, pages, video + media(f'<img src="{src}">'))

    items = await parser.apply_hashes(await parser.items)

    assert len(items) == 1
    assert items[0].title == "inst: example"
    assert items[0].link == parser.feed.url
    assert items[0].text == (
        f'example<br><img src="data:image/png;base64,{encoded}" alt="example" />'
    )
    assert items[0].hash == HashService.hash_str(encoded)


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("", "missing an image"),
        ("<img>", "missing src"),
        ('<img src=" ">', "missing src"),
        ('<img src="data:image/png;base64">', "data URI header"),
        ('<img src="data:text/html;base64,QQ==">', "data URI header"),
        ('<img src="data:image/png,hello">', "data URI header"),
        ('<img src="data:image/png;base64,@@@">', "invalid base64"),
        ('<img src="data:image/png;base64,">', "invalid image data"),
        ('<img src="data:image/png;base64,QQ==">', "invalid image data"),
    ],
)
async def test_anonyig_malformed_media_fails_whole_feed(
    anonyig_server, content, reason
):
    base_url, pages, encoded = anonyig_server
    valid = media(f'<img src="data:image/png;base64,{encoded}">')
    parser = parser_for(base_url, pages, valid + media(content))

    with pytest.raises(ValueError, match=reason):
        await parser.items


@pytest.mark.parametrize("path", ["failed.png", "disconnect.png"])
async def test_anonyig_download_failure_is_unavailable(anonyig_server, path, capsys):
    base_url, pages, encoded = anonyig_server
    valid = media(f'<img src="data:image/png;base64,{encoded}">')
    parser = parser_for(
        base_url,
        pages,
        valid + media(f'<img src="{base_url}/{path}?signature=secret">'),
    )

    with pytest.raises(FeedUnavailable) as caught:
        await parser.items

    assert caught.value.reason == "image_download_failed"
    assert caught.value.url == parser.feed.url
    assert "signature=secret" not in capsys.readouterr().out


async def test_anonyig_invalid_remote_image_fails(anonyig_server):
    base_url, pages, _ = anonyig_server
    parser = parser_for(base_url, pages, media(f'<img src="{base_url}/broken.png">'))

    with pytest.raises(ValueError, match="invalid image data"):
        await parser.items


@pytest.mark.parametrize(
    ("message", "reason"),
    [
        ("This profile is private", "private"),
        ("User not found", "not_found"),
        ("Something went wrong", "upstream_error"),
        ("No posts found. Please try again later", "upstream_error"),
        ("", "upstream_error"),
    ],
)
async def test_anonyig_error_result_is_unavailable(anonyig_server, message, reason):
    base_url, pages, _ = anonyig_server
    parser = parser_for(
        base_url,
        pages,
        f'<div class="error-message"><p class="error-message__text">{message}</p>'
        "<span>Advertisement</span></div>",
    )

    with pytest.raises(FeedUnavailable) as caught:
        await parser.items

    assert caught.value.reason == reason
    assert not parser.cache.has_valid_cache(parser._service_url)


@pytest.mark.parametrize("message", ["No posts", "No posts found."])
async def test_anonyig_explicit_empty_result(anonyig_server, message):
    base_url, pages, _ = anonyig_server
    parser = parser_for(
        base_url,
        pages,
        '<div class="error-message">'
        f'<p class="error-message__text">{message}</p><span>Advertisement</span></div>',
    )

    assert await parser.items == []


async def test_anonyig_unsupported_video_is_explicitly_skipped(anonyig_server, capsys):
    base_url, pages, _ = anonyig_server
    parser = parser_for(
        base_url,
        pages,
        media(
            '<span class="tags__item--video"></span>'
            '<a href="https://media.example/video.mp4?signature=secret">Video</a>'
        ),
    )

    assert await parser.items == []
    output = capsys.readouterr().out
    assert "unsupported_video" in output
    assert "signature=secret" not in output
