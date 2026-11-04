"""Public Instagram service contract against local HTTP responses."""

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from aiohttp import web
from structlog.testing import capture_logs

from app.extensions.parsers.exceptions import FeedUnavailable
from app.services.cache.storage.memory import MemoryStorage
from app.services.cache.temporary import TemporaryCacheService
from app.services.instagram import InstagramMedia, InstagramService

pytestmark = pytest.mark.integration

CRAWLER = "/example/"
API = "/api/v1/users/web_profile_info/"
FEED = "/api/v1/feed/user/example/username/"
EMBED = "/p/Ab_1/embed/captioned/"
IMAGE = "https://cdn.example/image.jpg"
SECOND_IMAGE = "https://cdn.example/second.jpg"
USER = {"username": "example", "id": "123", "is_private": False}
POST = {"shortcode": "Ab_1", "display_url": IMAGE}


def api_profile(posts, **user_fields):
    return {
        "status": "ok",
        "data": {
            "user": {
                **USER,
                "edge_owner_to_timeline_media": {
                    "count": len(posts),
                    "edges": [{"node": post} for post in posts],
                },
                **user_fields,
            }
        },
    }


def crawler_page(posts, count=None):
    objects = [
        USER,
        {
            "id": "123",
            "polaris_timeline_connection": {
                "count": len(posts) if count is None else count,
                "edges": [{"node": post} for post in posts],
            },
        },
    ]
    return (
        f'<html><script type="application/json">{json.dumps(objects)}</script></html>'
    )


@dataclass
class LocalInstagram:
    base_url: str = ""
    responses: dict = field(default_factory=dict)
    requests: Counter = field(default_factory=Counter)
    service: InstagramService = field(
        default_factory=lambda: InstagramService(
            "example", TemporaryCacheService[bytes](MemoryStorage())
        )
    )

    def respond(self, path, body, status=200, headers=None):
        self.responses[path] = (status, body, headers or {})


@pytest.fixture
async def instagram_server(monkeypatch):
    local = LocalInstagram()

    async def handle(request):
        local.requests[request.path] += 1
        status, body, headers = local.responses.get(
            request.path, (503, "unavailable", {})
        )
        if isinstance(body, (dict, list)):
            return web.json_response(body, status=status, headers=headers)
        return web.Response(text=body, status=status, headers=headers)

    app = web.Application()
    app.router.add_get("/{path:.*}", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    local.base_url = f"http://127.0.0.1:{runner.addresses[0][1]}"
    # Redirect only the remote boundary. HTTP, adapters and cooldown storage are real.
    monkeypatch.setattr(InstagramService, "_base_url", local.base_url)
    try:
        yield local
    finally:
        await runner.cleanup()


@pytest.mark.parametrize("source", [CRAWLER, API, FEED])
async def test_valid_sources_return_application_media(instagram_server, source):
    local = instagram_server
    if source == CRAWLER:
        payload = crawler_page([POST])
    elif source == API:
        payload = api_profile([POST])
    else:
        payload = {"status": "ok", "user": USER, "items": [POST]}
    local.respond(source, payload)

    assert await local.service.get_media() == [
        InstagramMedia(IMAGE, f"{local.base_url}/p/Ab_1/")
    ]
    assert local.requests[source] == 1
    assert local.requests[EMBED] == 0


@pytest.mark.parametrize(
    ("post", "shortcode", "urls"),
    [
        (
            {
                "code": "Ab_1",
                "carousel_media": [
                    {"image_versions2": {"candidates": [{"url": IMAGE}]}},
                    {"display_uri": SECOND_IMAGE},
                ],
            },
            "Ab_1",
            [IMAGE, SECOND_IMAGE],
        ),
        (
            {
                "shortcode": "Ab_1",
                "edge_sidecar_to_children": {
                    "edges": [
                        {"node": {"display_url": IMAGE}},
                        {"node": {"thumbnail_src": SECOND_IMAGE}},
                    ]
                },
            },
            "Ab_1",
            [IMAGE, SECOND_IMAGE],
        ),
        ({"pk": 1, "thumbnail_src": IMAGE}, "B", [IMAGE]),
        (
            {
                "seo_canonical_url": "https://www.instagram.com/reel/Ab_1/",
                "display_url": IMAGE,
            },
            "Ab_1",
            [IMAGE],
        ),
    ],
)
async def test_remote_post_shapes_preserve_order(
    instagram_server, post, shortcode, urls
):
    local = instagram_server
    local.respond(FEED, {"items": [{**post, "user": USER}]})

    assert await local.service.get_media() == [
        InstagramMedia(url, f"{local.base_url}/p/{shortcode}/") for url in urls
    ]


@pytest.mark.parametrize("source", [CRAWLER, API, FEED])
async def test_confirmed_empty_profiles_succeed(instagram_server, source):
    local = instagram_server
    payloads = {
        CRAWLER: crawler_page([]),
        API: api_profile([]),
        FEED: {
            "user": {**USER, "media_count": 0},
            "items": [],
            "more_available": False,
        },
    }
    local.respond(source, payloads[source])

    assert await local.service.get_media() == []
    assert local.requests[source] == 1


@pytest.mark.parametrize("source", [API, FEED])
async def test_private_profile_is_distinct_from_empty(instagram_server, source):
    local = instagram_server
    payload = api_profile([], is_private=True)
    if source == FEED:
        payload = {"user": {**USER, "is_private": True}, "items": []}
    local.respond(source, payload)

    with pytest.raises(FeedUnavailable) as raised:
        await local.service.get_media()
    assert raised.value.reason == "private_profile"
    assert raised.value.retry_at is not None
    assert raised.value.retry_at > datetime.now(UTC)


@pytest.mark.parametrize(
    ("source", "body", "reason"),
    [
        (API, "{broken", "invalid_response"),
        (API, [], "invalid_response"),
        (API, {"data": None}, "missing_profile"),
        (API, api_profile([], username="another"), "missing_profile"),
        (API, api_profile([], is_private="false"), "invalid_profile"),
        (API, api_profile([], media_count="1"), "invalid_media_count"),
        (
            API,
            api_profile([], edge_owner_to_timeline_media={"edges": []}),
            "unverified_empty_timeline",
        ),
        (
            API,
            api_profile(
                [], edge_owner_to_timeline_media={"count": 0, "edges": [{"node": None}]}
            ),
            "invalid_timeline",
        ),
        (API, api_profile([{"display_url": IMAGE}]), "invalid_shortcode"),
        (API, api_profile([{**POST, "shortcode": ""}]), "invalid_shortcode"),
        (API, api_profile([{**POST, "display_url": 12}]), "invalid_media_url"),
        (API, api_profile([{**POST, "display_url": ""}]), "invalid_media_url"),
        (
            API,
            api_profile([{**POST, "display_url": "javascript:alert(1)"}]),
            "invalid_media_url",
        ),
        (
            API,
            api_profile(
                [
                    {
                        **POST,
                        "edge_sidecar_to_children": {
                            "edges": [{"node": {"display_url": IMAGE}}, {"node": None}]
                        },
                    }
                ]
            ),
            "invalid_carousel",
        ),
        (FEED, {"user": USER, "items": [POST, None]}, "invalid_timeline"),
        (
            FEED,
            {"user": USER, "items": [{**POST, "user": {"username": "another"}}]},
            "profile_mismatch",
        ),
        (
            FEED,
            {"user": {**USER, "media_count": 0}, "items": [], "more_available": True},
            "unverified_empty_timeline",
        ),
        (
            FEED,
            {
                "user": USER,
                "items": [
                    {"code": "Ab_1", "image_versions2": {"candidates": [{"url": None}]}}
                ],
            },
            "invalid_media_url",
        ),
        (
            CRAWLER,
            '<script type="application/json">{broken</script>',
            "missing_profile",
        ),
        (CRAWLER, crawler_page([], count=5), "unverified_empty_timeline"),
    ],
)
async def test_malformed_sources_raise_instead_of_returning_empty(
    instagram_server, source, body, reason
):
    local = instagram_server
    local.respond(source, body)

    with capture_logs() as logs, pytest.raises(FeedUnavailable) as raised:
        await local.service.get_media()

    assert raised.value.reason == "profile_unavailable"
    assert raised.value.retry_at is None
    assert any(
        log.get("source")
        == {API: "profile-api", FEED: "profile-feed", CRAWLER: "crawler"}[source]
        and log.get("reason") == reason
        for log in logs
    )
    assert local.requests[FEED] == 1


async def test_malformed_api_can_fall_back_to_valid_feed(instagram_server):
    local = instagram_server
    local.respond(
        API, api_profile([{**POST, "display_url": None, "carousel_media": [None]}])
    )
    local.respond(FEED, {"user": USER, "items": [POST]})

    assert await local.service.get_media() == [
        InstagramMedia(IMAGE, f"{local.base_url}/p/Ab_1/")
    ]


@pytest.mark.parametrize("serialized", [False, True])
async def test_missing_media_is_enriched_by_typed_embed(instagram_server, serialized):
    local = instagram_server
    local.respond(API, api_profile([{"shortcode": "Ab_1"}]))
    data = {"graphql": {"shortcode_media": POST}}
    if serialized:
        data = {"require": [json.dumps(data)]}
    local.respond(EMBED, f"<script>{json.dumps(data)}</script>")

    assert await local.service.get_media() == [
        InstagramMedia(IMAGE, f"{local.base_url}/p/Ab_1/")
    ]
    assert local.requests[EMBED] == 1


@pytest.mark.parametrize(
    "embed_body",
    [
        "<html>login</html>",
        '<script>{"shortcode_media":{"shortcode":"other","display_url":"https://cdn.example/image.jpg"}}</script>',
    ],
)
async def test_unusable_embed_cannot_succeed_with_partial_media(
    instagram_server, embed_body
):
    local = instagram_server
    local.respond(API, api_profile([POST, {"shortcode": "Ab_1"}]))
    local.respond(EMBED, embed_body)

    with pytest.raises(FeedUnavailable) as raised:
        await local.service.get_media()
    assert raised.value.reason == "profile_unavailable"


@pytest.mark.parametrize("body", ["{broken", {"status": "fail"}])
async def test_rate_limit_precedes_payload_errors_and_preserves_cooldown(
    instagram_server, body
):
    local = instagram_server
    for source in (API, FEED):
        local.respond(source, body, status=429, headers={"Retry-After": "120"})

    with capture_logs() as logs:
        for _ in range(2):
            before = datetime.now(UTC)
            error = await unavailable(local.service)
            assert error.reason == "profile_unavailable"
            assert error.retry_at is not None
            assert before + timedelta(seconds=110) < error.retry_at
            assert error.retry_at <= datetime.now(UTC) + timedelta(seconds=120)

    assert local.requests[API] == local.requests[FEED] == 1
    assert local.requests[CRAWLER] == 2
    summaries = [log for log in logs if log["event"] == "instagram_profile_unavailable"]
    assert summaries[0]["profile_api_outcome"] == "rate-limited"
    assert summaries[1]["profile_api_outcome"] == "skipped:rate-limited"


async def test_rate_limited_api_can_fall_back_to_feed(instagram_server):
    local = instagram_server
    local.respond(API, "{broken", status=429)
    local.respond(FEED, {"user": USER, "items": [POST]})

    assert await local.service.get_media() == [
        InstagramMedia(IMAGE, f"{local.base_url}/p/Ab_1/")
    ]


async def unavailable(service):
    with pytest.raises(FeedUnavailable) as raised:
        await service.get_media()
    return raised.value
