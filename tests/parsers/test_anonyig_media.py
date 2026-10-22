import base64
from collections import Counter
from dataclasses import dataclass, field
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from threading import Thread
from urllib.parse import urlsplit

import pytest
from bs4 import BeautifulSoup
from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.service import Service

import app.configs  # noqa: F401  # Initialize the dependency container.
from app.extensions.parsers.exceptions import FeedUnavailable
from app.parsers.instagram import AnonyigInstagramFeed
from app.serializers.feed import Feed
from app.services.container import Container
from app.services.http import HttpService

pytestmark = pytest.mark.integration


@dataclass
class MediaSource:
    base_url: str = ""
    media: str = ""
    image_status: int = 200
    video_status: int = 200
    requests: Counter = field(default_factory=Counter)
    image: bytes = b""

    def parser(self, username: str = "fixture_account") -> AnonyigInstagramFeed:
        feed = Feed(
            id=1,
            title="Local Anonyig",
            type="inst",
            url=f"https://www.instagram.com/{username}",
        )
        parser = AnonyigInstagramFeed(feed, {})
        parser._service_url = self.base_url
        return parser

    def photo(self, src: str) -> str:
        return (
            '<div class="profile-media-list__item">'
            f'<img src="{escape(src, quote=True)}"></div>'
        )


@pytest.fixture
def media_source(monkeypatch):
    # Configure only the browser dependency. Parsing, HTTP, image validation and
    # hashing run unchanged against the local source.
    def browser():
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        return webdriver.Chrome(
            service=Service("/usr/bin/chromedriver"), options=options
        )

    monkeypatch.setattr(Container.get_data(), "selenium_web_driver", browser)
    output = BytesIO()
    Image.new("RGB", (2, 2), "blue").save(output, format="PNG")
    source = MediaSource(image=output.getvalue())

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            source.requests[self.path] += 1
            path = urlsplit(self.path).path
            if path == "/photo":
                status, body, content_type = (
                    source.image_status,
                    source.image,
                    "image/png",
                )
            elif path in ("/video", "/video.mp4"):
                status, body, content_type = (
                    source.video_status,
                    b"expired",
                    "video/mp4",
                )
            else:
                status, content_type = 200, "text/html; charset=utf-8"
                body = (
                    '<form class="search-form">'
                    '<input class="search-form__input">'
                    '<button type="button" class="search-form__button">Search</button>'
                    '</form><div class="search-result">'
                    f'<div class="profile-media-list">{source.media}</div></div>'
                ).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            # Browser subresource loading must not prefetch the media under test.
            # Only the parser's HTTP client can download it.
            self.send_header("Content-Security-Policy", "default-src 'none'")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    source.base_url = f"http://127.0.0.1:{server.server_port}"
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield source
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize(
    "contents",
    [
        '<a class="download-btn" href="{base}/video?token={token}">Download</a>',
        (
            '<a class="download-btn" href="{base}/video.mp4?token={token}">Download</a>'
            '<img src="{base}/photo?token={token}">'
        ),
        '<a class="download-btn">Download</a>',
        (
            '<a class="download-btn" href="javascript:alert(1)">Download</a>'
            '<img src="data:image/png;base64,invalid">'
        ),
    ],
)
async def test_videos_are_skipped_even_without_thumbnail_or_valid_links(
    media_source, contents
):
    for token, status in [("original", 200), ("rotated", 403)]:
        media_source.video_status = status
        media_source.image_status = status
        video_path = f"/video?token={token}"
        actual_status, _ = await HttpService.get_with_status(
            media_source.base_url + video_path
        )
        assert actual_status == status
        video = contents.format(base=media_source.base_url, token=token)
        media_source.media = (
            '<div class="profile-media-list__item">'
            f'<span class="tags__item--video">Video</span>{video}</div>'
        )
        parser = media_source.parser()
        assert await parser.apply_hashes(await parser.items) == []
        assert media_source.requests[video_path] == 1

    assert not any(
        path.startswith(("/video.mp4", "/photo")) for path in media_source.requests
    )


async def test_image_identity_survives_token_rotation_and_source_expiry(media_source):
    snapshots = []
    for token in ["original", "rotated"]:
        src = f"{media_source.base_url}/photo?token={token}&expires=soon"
        media_source.media = media_source.photo(src)
        parser = media_source.parser()
        items = await parser.apply_hashes(await parser.items)
        assert len(items) == 1
        assert items[0].hash
        assert src not in items[0].text
        snapshots.append(items[0])

    assert snapshots[0].hash == snapshots[1].hash
    assert snapshots[0].text == snapshots[1].text
    assert media_source.requests["/photo?token=original&expires=soon"] == 1
    assert media_source.requests["/photo?token=rotated&expires=soon"] == 1

    media_source.image_status = 403
    status, _ = await HttpService.get_with_status(src)
    assert status == 403
    for item in snapshots:
        image = BeautifulSoup(item.text, "html.parser").select_one("img")
        assert image is not None
        header, encoded = str(image["src"]).split(",", 1)
        assert header == "data:image/png;base64"
        assert base64.b64decode(encoded, validate=True) == media_source.image

    inline_src = (
        "data:image/png;base64," + base64.b64encode(media_source.image).decode()
    )
    media_source.media = media_source.photo(inline_src)
    parser = media_source.parser()
    (inline_item,) = await parser.apply_hashes(await parser.items)
    assert inline_item.hash == snapshots[0].hash


async def test_escaping_preserves_text_and_prevents_attribute_injection(media_source):
    username = 'account" onerror="alert(1)&<svg>'
    media_source.media = media_source.photo(
        f"{media_source.base_url}/photo?token=one&other=two"
    )
    (item,) = await media_source.parser(username).items
    soup = BeautifulSoup(item.text, "html.parser")
    image = soup.select_one("img")
    assert image is not None
    assert set(image.attrs) == {"src", "alt"}
    assert image["alt"] == username
    assert soup.get_text() == username
    assert [tag.name for tag in soup.select("*")] == ["br", "img"]
    assert "&quot;" in item.text
    assert "&amp;" in item.text
    assert "&lt;svg&gt;" in item.text


@pytest.mark.parametrize(
    "src",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "//example.invalid/photo.png",
        "https:///photo.png",
        "http://[broken/photo.png",
        "http://127.0.0.1:invalid/photo",
        "http://127.0.0.1:65536/photo",
        "http://127.0.0.1:0/photo",
        "http://user:password@127.0.0.1/photo",
        "http://127.0.0.1/has space",
        "http://127.0.0.1/has\\backslash",
        'http://127.0.0.1/photo" onerror="alert(1)',
    ],
)
async def test_unsafe_or_malformed_image_urls_fail(media_source, src):
    media_source.media = media_source.photo(src)
    with pytest.raises(ValueError, match="invalid URL"):
        await media_source.parser().items


@pytest.mark.parametrize(
    "contents",
    [
        "",
        "<img>",
        '<img src="">',
        '<img src="data:text/html;base64,PHNjcmlwdD4=">',
        '<img src="data:image/png;base64,invalid">',
    ],
)
async def test_missing_or_invalid_image_data_fails(media_source, contents):
    media_source.media = f'<div class="profile-media-list__item">{contents}</div>'
    with pytest.raises(ValueError):
        await media_source.parser().items


async def test_expired_image_source_raises_instead_of_returning_empty_feed(
    media_source,
):
    media_source.image_status = 403
    media_source.media = media_source.photo(f"{media_source.base_url}/photo?expired=1")
    with pytest.raises(FeedUnavailable, match="image_download_failed"):
        await media_source.parser().items
    assert media_source.requests["/photo?expired=1"] == 1
