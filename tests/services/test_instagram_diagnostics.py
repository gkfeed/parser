import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import TypedDict

import pytest
from aiohttp import web
from structlog.testing import capture_logs

from app.extensions.parsers.exceptions import FeedUnavailable
from app.services.cache.storage.memory import MemoryStorage
from app.services.cache.temporary import TemporaryCacheService
from app.services.instagram import InstagramService

pytestmark = pytest.mark.integration

SECRET = "sensitive-response-value"
PROFILE = {"username": "example", "id": "123", "is_private": False}
TIMELINE = {"id": "123", "polaris_timeline_connection": {"edges": []}}


class Responses(TypedDict):
    crawler: str
    api_status: int
    api_body: dict


def page(component="PolarisErrorRoot.react", props=None, objects=(), markup=""):
    data = [
        {"rootView": {"resource": {"__dr": component}, "props": props or {}}},
        *objects,
    ]
    return f'<html>{markup}<script type="application/json">{json.dumps(data)}</script></html>'


@pytest.fixture
async def instagram_server(monkeypatch):
    requests = Counter()
    responses: Responses = {
        "crawler": page(),
        "api_status": 401,
        "api_body": {"status": "fail", "require_login": True, "message": SECRET},
    }

    async def handle(request):
        requests[request.path] += 1
        if request.path == "/example/":
            return web.Response(text=responses["crawler"], content_type="text/html")
        return web.json_response(responses["api_body"], status=responses["api_status"])

    app = web.Application()
    app.router.add_get("/{path:.*}", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    monkeypatch.setattr(
        InstagramService, "_base_url", f"http://127.0.0.1:{runner.addresses[0][1]}"
    )
    try:
        yield responses, requests, TemporaryCacheService[bytes](MemoryStorage())
    finally:
        await runner.cleanup()


@pytest.mark.parametrize(
    ("html", "outcome"),
    [
        (page(props={"failure_reason": SECRET}), "error_page"),
        (page("PolarisLoggedOutMobileGatedBlockRoot.react"), "logged_out_gate"),
        (page(props={"restricted_age": 18}), "age_restricted"),
        (
            page(markup=f'<form action="/accounts/login/?next={SECRET}"></form>'),
            "login_page",
        ),
        (page(markup=f'<form action="/challenge/{SECRET}"></form>'), "challenge_page"),
        (page(component=SECRET), "missing_profile"),
        ('<script type="application/json">{broken</script>', "missing_profile"),
    ],
)
async def test_unavailable_pages_have_specific_safe_diagnostics(
    instagram_server, html, outcome
):
    responses, requests, cache = instagram_server
    responses["crawler"] = html

    with capture_logs() as logs, pytest.raises(FeedUnavailable) as raised:
        await InstagramService("example", cache).get_media()

    assert raised.value.reason == "profile_unavailable"
    assert raised.value.retry_at is not None
    assert raised.value.retry_at > datetime.now(UTC)
    summary = next(
        log for log in logs if log["event"] == "instagram_profile_unavailable"
    )
    assert summary["crawler_outcome"] == outcome
    assert summary["profile_api_outcome"] == "authentication-required"
    assert summary["profile_feed_outcome"] == "authentication-required"
    assert sum(requests.values()) == 3
    assert SECRET not in json.dumps(logs)


async def test_partial_profile_reports_extraction_evidence(instagram_server):
    responses, _, cache = instagram_server
    responses["crawler"] = page(
        "PolarisProfilePostsLoggedOutTabGridRoot.react",
        objects=[
            {"username": "example"},
            {"username": "example", "id": "123"},
            TIMELINE,
        ],
    )

    with capture_logs() as logs, pytest.raises(FeedUnavailable):
        await InstagramService("example", cache).get_media()

    failure = next(log for log in logs if log["event"] == "instagram_request_failed")
    assert failure["reason"] == "missing_profile"
    assert failure["page_state"] == "profile_page"
    assert failure["matching_profiles"] == 0
    assert failure["matching_username_objects"] == 2
    assert failure["matching_id_profiles"] == 1
    assert failure["matching_privacy_profiles"] == 0
    assert failure["timeline_objects"] == 1


async def test_error_root_cannot_confirm_empty_profile(instagram_server):
    responses, _, cache = instagram_server
    responses["crawler"] = page(objects=[{**PROFILE, "media_count": 0}, TIMELINE])

    with capture_logs() as logs, pytest.raises(FeedUnavailable):
        await InstagramService("example", cache).get_media()

    assert not any(log["event"] == "instagram_profile_fetched" for log in logs)


@pytest.mark.parametrize("private", [False, True])
async def test_valid_profile_preserves_confirmed_empty_and_private_results(
    instagram_server, private
):
    responses, requests, cache = instagram_server
    responses["crawler"] = page(
        "PolarisProfilePostsLoggedOutTabGridRoot.react",
        objects=[{**PROFILE, "is_private": private, "media_count": 0}, TIMELINE],
        markup='<a href="/accounts/login/">Login</a><form action="http://[invalid"></form>',
    )

    if private:
        with pytest.raises(FeedUnavailable, match="private_profile"):
            await InstagramService("example", cache).get_media()
    else:
        assert await InstagramService("example", cache).get_media() == []

    assert sum(requests.values()) == 1


async def test_cooldown_skips_then_retries_expired_sources_with_media_fallback(
    instagram_server,
):
    responses, requests, cache = instagram_server
    for source in ("profile-api", "profile-feed"):
        cache.set_with_expiry(
            f"instagram:{source}:rate-limited", b"1", timedelta(hours=1)
        )

    with capture_logs() as logs, pytest.raises(FeedUnavailable):
        await InstagramService("example", cache).get_media()

    skips = [log for log in logs if log["event"] == "instagram_api_skipped"]
    assert len(skips) == 2
    assert all(log["rate_limit_cooldown_state"] == "active" for log in skips)
    assert all(0 < log["cooldown_remaining_seconds"] <= 3600 for log in skips)
    assert sum(requests.values()) == 1

    for source in ("profile-api", "profile-feed"):
        cache.set_with_expiry(
            f"instagram:{source}:rate-limited", b"1", timedelta(seconds=-1)
        )
    responses["api_status"] = 200
    responses["api_body"] = {
        "status": "ok",
        "data": {
            "user": {
                **PROFILE,
                "edge_owner_to_timeline_media": {
                    "edges": [
                        {
                            "node": {
                                "shortcode": "post",
                                "display_url": "https://example.org/image.jpg",
                            }
                        }
                    ]
                },
            }
        },
    }

    with capture_logs() as logs:
        media = await InstagramService("example", cache).get_media()

    assert len(media) == 1
    assert media[0].url == "https://example.org/image.jpg"
    fetched = next(log for log in logs if log["event"] == "instagram_profile_fetched")
    assert fetched["source"] == "profile-api"
    assert fetched["fallback_used"] is True
    assert fetched["rate_limit_cooldown_state"] == "expired"
    assert fetched["authentication_cooldown_state"] == "missing"
    assert sum(requests.values()) == 3


async def test_expired_authentication_cooldowns_are_retried_and_refusal_is_renewed(
    instagram_server,
):
    _, requests, cache = instagram_server
    for source in ("profile-api", "profile-feed"):
        cache.set_with_expiry(
            f"instagram:{source}:authentication-required", b"1", timedelta(seconds=-1)
        )

    with capture_logs() as logs, pytest.raises(FeedUnavailable):
        await InstagramService("example", cache).get_media()

    pauses = [log for log in logs if log["event"] == "instagram_api_paused"]
    assert len(pauses) == 2
    assert all(log["authentication_cooldown_state"] == "expired" for log in pauses)
    assert all(log["reason"] == "authentication-required" for log in pauses)
    assert all(log["require_login"] is True for log in pauses)
    assert sum(requests.values()) == 3

    with capture_logs() as logs, pytest.raises(FeedUnavailable):
        await InstagramService("example", cache).get_media()

    skips = [log for log in logs if log["event"] == "instagram_api_skipped"]
    assert len(skips) == 2
    assert all(log["authentication_cooldown_state"] == "active" for log in skips)
    assert sum(requests.values()) == 4
