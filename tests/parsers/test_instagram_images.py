import base64
import hashlib
import json
import random
import re
from io import BytesIO

import pytest
from aiohttp import web
from PIL import Image

from app.extensions.parsers.exceptions import FeedUnavailable
from app.parsers.instagram import InstagramFeed
from app.serializers.feed import Feed
from app.services.image import ImageService
from app.services.instagram import InstagramService
from app.utils.datetime import constant_datetime

pytestmark = pytest.mark.integration


def image_bytes(image: Image.Image, format: str, **kwargs) -> bytes:
    output = BytesIO()
    image.save(output, format=format, **kwargs)
    return output.getvalue()


@pytest.fixture
async def image_server(monkeypatch):
    noise = random.Random(0).randbytes(256 * 192 * 4)
    oriented = Image.frombytes("RGBA", (256, 192), noise)
    exif = Image.Exif()
    exif[274] = 6
    png = image_bytes(oriented, "PNG", exif=exif)
    jpeg = image_bytes(Image.new("RGB", (64, 32), "red"), "JPEG")
    tiny = image_bytes(Image.new("P", (1, 1)), "GIF")
    oversized = image_bytes(Image.new("L", (5000, 4001)), "PNG")
    payloads = {
        "png": (200, "image/png", png),
        # MIME comes from the image bytes, even if the server labels them JPEG.
        "mislabeled": (200, "IMAGE/JPEG; charset=binary", png),
        "jpeg": (200, "image/jpeg", jpeg),
        "tiny": (200, "image/gif", tiny),
        "corrupt": (200, "image/png", b"not an image"),
        "truncated": (200, "image/png", png[:100]),
        "pixels": (200, "image/png", oversized),
        "download-limit": (200, "image/png", b"x" * (20 * 1024 * 1024 + 1)),
        "unavailable": (503, "image/png", png),
        "not-image": (200, "text/html", b"<html>login required</html>"),
        "empty": (200, "image/png", b""),
    }

    async def profile(request):
        username = request.match_info["username"]
        node = {
            "id": "123",
            "username": username,
            "is_private": False,
            "polaris_timeline_connection": {
                "edges": [
                    {
                        "node": {
                            "shortcode": "post",
                            "display_url": f"{base_url}/images/{username}",
                        }
                    }
                ]
            },
        }
        return web.Response(
            text=f'<script type="application/json">{json.dumps(node)}</script>',
            content_type="text/html",
        )

    async def serve_image(request):
        status, content_type, body = payloads[request.match_info["name"]]
        return web.Response(
            status=status, body=body, headers={"Content-Type": content_type}
        )

    app = web.Application()
    app.router.add_get("/images/{name}", serve_image)
    app.router.add_get("/{username}/", profile)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    host, port = runner.addresses[0]
    base_url = f"http://{host}:{port}"
    # Redirect only the external endpoint; HTTP, parsing and Pillow remain real.
    monkeypatch.setattr(InstagramService, "_base_url", base_url)
    try:
        yield base_url, payloads
    finally:
        await runner.cleanup()


def parser_for(base_url: str, username: str) -> InstagramFeed:
    feed = Feed(id=1, title="Instagram", type="inst", url=f"{base_url}/{username}/")
    return InstagramFeed(feed, {})


@pytest.mark.parametrize(
    ("username", "mime_type"),
    [("png", "image/png"), ("mislabeled", "image/png"), ("jpeg", "image/jpeg")],
)
async def test_instagram_embeds_original_bytes_and_hash(
    image_server, username, mime_type
):
    base_url, payloads = image_server
    parser = parser_for(base_url, username)
    content = payloads[username][2]
    encoded = base64.b64encode(content).decode()

    items = await parser.apply_hashes(await parser.items)

    assert len(items) == 1
    item = items[0]
    assert item.title == f"inst: {username}"
    assert item.text == (
        f'{username}<br><img src="data:{mime_type};base64,{encoded}" alt="{username}" />'
    )
    assert item.link == f"{base_url}/p/post/"
    assert item.date == constant_datetime
    assert item.hash == hashlib.sha256(encoded.encode()).hexdigest()
    restored = item.model_copy(update={"hash": None})
    assert (await parser.apply_hashes([restored]))[0].hash == item.hash


@pytest.mark.parametrize(
    ("username", "attempt", "max_dimension"), [("png", 1, 256), ("png", 12, 128)]
)
async def test_instagram_compresses_to_oriented_rgb_jpeg_and_preserves_item(
    image_server, username, attempt, max_dimension
):
    base_url, payloads = image_server
    parser = parser_for(base_url, username)
    originals = await parser.items
    snapshot = originals[0].model_dump()

    reduced = await parser.reduce_result_size(originals, attempt)

    assert reduced is not None
    assert originals[0].model_dump() == snapshot
    item = reduced[0]
    assert item.model_dump(exclude={"text"}) == originals[0].model_dump(
        exclude={"text"}
    )
    match = re.search(r'src="data:image/jpeg;base64,([^"]+)"', item.text)
    assert match is not None
    content = base64.b64decode(match[1], validate=True)
    assert len(content) < len(payloads[username][2])
    with Image.open(BytesIO(content)) as image:
        assert image.format == "JPEG"
        assert image.mode == "RGB"
        assert image.height > image.width
        assert max(image.size) <= max_dimension
        image.load()
    assert (await parser.apply_hashes(reduced))[0].hash == snapshot["hash"]
    assert await parser.reduce_result_size(originals, attempt) == reduced


async def test_instagram_keeps_smaller_original_and_handles_non_image_items(
    image_server,
):
    base_url, _ = image_server
    parser = parser_for(base_url, "tiny")
    originals = await parser.items

    assert await parser.reduce_result_size(originals, 1) == originals
    plain = originals[0].model_copy(update={"text": "No embedded image"})
    assert await parser.reduce_result_size([plain], 1) is None
    assert await parser.reduce_result_size([], 1) is None


@pytest.mark.parametrize(
    ("username", "reason"),
    [
        ("unavailable", "invalid_image_response"),
        ("not-image", "invalid_image_response"),
        ("download-limit", "image_download_failed"),
    ],
)
async def test_instagram_reports_image_source_failures(image_server, username, reason):
    base_url, _ = image_server
    parser = parser_for(base_url, username)

    with pytest.raises(FeedUnavailable) as caught:
        await parser.items

    assert caught.value.url == parser.feed.url
    assert caught.value.reason == reason
    assert caught.value.retry_at is None
    assert caught.value.__cause__ is not None


@pytest.mark.parametrize("username", ["corrupt", "truncated", "pixels", "empty"])
async def test_instagram_rejects_invalid_image_data_with_feed_context(
    image_server, username
):
    base_url, _ = image_server
    parser = parser_for(base_url, username)

    with pytest.raises(ValueError, match="Invalid Instagram image") as caught:
        await parser.items

    assert parser.feed.url in str(caught.value)
    assert caught.value.__cause__ is not None
    if username == "pixels":
        assert "pixel limit" in str(caught.value)


@pytest.mark.parametrize(
    "encoded", ["%%%", base64.b64encode(b"invalid image").decode()]
)
async def test_instagram_rejects_damaged_embedded_images(image_server, encoded):
    base_url, _ = image_server
    parser = parser_for(base_url, "png")
    originals = await parser.items
    damaged = originals[0].model_copy(
        update={"text": f'<img src="data:image/png;base64,{encoded}" />'}
    )

    with pytest.raises(ValueError, match="Cannot reduce Instagram image") as caught:
        await parser.reduce_result_size([damaged], 1)

    assert parser.feed.url in str(caught.value)
    assert caught.value.__cause__ is not None


async def test_image_service_download_and_resize_contract(image_server):
    base_url, payloads = image_server

    original = await ImageService.download(f"{base_url}/images/mislabeled")
    resized = await ImageService.resize(original, len(original.content) // 2)

    assert original.content == payloads["png"][2]
    assert original.mime_type == "image/png"
    assert base64.b64decode(original.encoded, validate=True) == original.content
    assert original.data_url == f"data:image/png;base64,{original.encoded}"
    assert resized.mime_type == "image/jpeg"
    assert len(resized.content) <= len(original.content) // 2
    assert resized.data_url.startswith("data:image/jpeg;base64,")
