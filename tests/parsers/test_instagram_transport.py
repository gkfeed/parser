import base64
import hashlib
import json
import random
from collections import Counter
from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Any

import pytest
from aiohttp import web
from bs4 import BeautifulSoup
from bs4.element import Tag
from PIL import Image

from app.core.worker import _process_feed
from app.extensions.parsers.exceptions import FeedUnavailable
from app.serializers.feed import Feed, FeedResult
from app.services.broker import BrokerService, Task
from app.services.cache.storage.memory import MemoryStorage
from app.services.cache.temporary import TemporaryCacheService
from app.services.instagram import InstagramService

pytestmark = pytest.mark.integration


@pytest.fixture
async def instagram_server(monkeypatch):
    state: dict[str, Any] = {
        "crawler": "<html><title>Instagram</title></html>",
        "api_status": 429,
        "feed_status": 401,
        "requests": Counter(),
        "submissions": [],
        "results": [],
        "errors": [],
        "limit": 50_000_000,
    }

    async def handle(request):
        state["requests"][request.path] += 1
        if request.path == "/submit_result":
            body = await request.read()
            state["submissions"].append(len(body))
            if len(body) > state["limit"]:
                return web.Response(status=413)
            payload = json.loads(body)
            state["results"].append(FeedResult.model_validate_json(payload["result"]))
            return web.json_response({})
        if request.path == "/submit_error":
            state["errors"].append(await request.json())
            return web.json_response({})
        if request.path == "/image.jpg":
            return web.Response(body=state["image"], content_type="image/jpeg")
        if request.path == "/api/v1/users/web_profile_info/":
            return web.json_response(
                {"status": "fail"},
                status=state["api_status"],
                headers={"Retry-After": "7200"},
            )
        if request.path.startswith("/api/v1/feed/user/"):
            return web.json_response({"status": "fail"}, status=state["feed_status"])
        return web.Response(text=state["crawler"], content_type="text/html")

    app = web.Application(client_max_size=128 * 1024 * 1024)
    app.router.add_route("*", "/{path:.*}", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    host, port = runner.addresses[0]
    state["url"] = f"http://{host}:{port}"
    # Redirect only the external Instagram boundary to the isolated HTTP server.
    monkeypatch.setattr(InstagramService, "_base_url", state["url"])
    try:
        yield state
    finally:
        await runner.cleanup()


def crawler_profile(server, count):
    timeline = {
        "edges": [
            {
                "node": {
                    "shortcode": f"post{i}",
                    "display_url": server["url"] + "/image.jpg",
                }
            }
            for i in range(count)
        ],
        "page_info": {"has_next_page": False},
    }
    profile = {
        "id": "123",
        "username": "example",
        "is_private": False,
        "polaris_timeline_connection": timeline,
    }
    return (
        f'<meta property="og:description" content="1 Followers, 1 Following, '
        f'{count} Posts - Instagram (@example)">'
        f'<script type="application/json">{json.dumps(profile)}</script>'
    )


@pytest.fixture
def large_image():
    pixels = random.Random(1).randbytes(1600 * 1200 * 3)
    image = Image.frombytes("RGB", (1600, 1200), pixels)
    output = BytesIO()
    image.save(output, "JPEG", quality=98)
    return output.getvalue()


@pytest.mark.parametrize(("count", "limit"), [(30, 50_000_000), (1, 200_000)])
async def test_instagram_image_result_transport(
    instagram_server, large_image, count, limit
):
    server = instagram_server
    server["image"] = large_image
    server["limit"] = limit
    server["crawler"] = crawler_profile(server, count)
    feed = Feed(
        id=1, title="Instagram", url="https://instagram.com/example", type="inst"
    )

    await _process_feed(
        Task("isolated-instagram", "", []), feed, BrokerService(server["url"])
    )

    assert not server["errors"]
    assert len(server["results"]) == 1
    result = server["results"][0]
    assert len(result.items) == count
    assert server["submissions"][-1] <= limit
    if count == 30:
        # The observed production retry succeeded at 49.4 MB. Stay below that
        # size on the first submission, even with 30 multi-megabyte originals.
        assert len(server["submissions"]) == 1
    else:
        assert len(server["submissions"]) > 1
    original_hash = hashlib.sha256(base64.b64encode(large_image)).hexdigest()
    for item in result.items:
        assert item.hash == original_hash
        assert item.link.startswith(server["url"] + "/p/post")
        img = BeautifulSoup(item.text, "html.parser").find("img")
        assert isinstance(img, Tag)
        src = img.get("src")
        assert isinstance(src, str)
        content = base64.b64decode(src.split(",", 1)[1], validate=True)
        assert len(content) <= 1024 * 1024
        with Image.open(BytesIO(content)) as image:
            image.verify()


async def test_instagram_cooldowns_keep_crawler_fallback_available(instagram_server):
    server = instagram_server
    cache = TemporaryCacheService(storage=MemoryStorage())
    before = datetime.now(UTC)
    for username in ("example", "another"):
        with pytest.raises(FeedUnavailable) as error:
            await InstagramService(username, cache).get_media()
        assert error.value.reason == "profile_unavailable"
        assert error.value.retry_at is not None
        assert before + timedelta(minutes=59) < error.value.retry_at
        assert error.value.retry_at < datetime.now(UTC) + timedelta(hours=1, seconds=1)

    assert server["requests"]["/api/v1/users/web_profile_info/"] == 1
    assert server["requests"]["/api/v1/feed/user/example/username/"] == 1
    assert server["requests"]["/api/v1/feed/user/another/username/"] == 0
    server["crawler"] = crawler_profile(server, 1)
    media = await InstagramService("example", cache).get_media()
    assert len(media) == 1
    assert media[0].url == server["url"] + "/image.jpg"
    assert server["requests"]["/api/v1/users/web_profile_info/"] == 1


async def test_instagram_verified_zero_posts(instagram_server):
    server = instagram_server
    server["crawler"] = crawler_profile(server, 0)
    cache = TemporaryCacheService(storage=MemoryStorage())

    assert await InstagramService("example", cache).get_media() == []
    assert not any(path.startswith("/api/") for path in server["requests"])
