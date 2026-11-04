"""Instagram refusal diagnostics through the public service and local HTTP."""

import json
from datetime import timedelta

import pytest
from structlog.testing import capture_logs

from app.extensions.parsers.exceptions import FeedUnavailable
from app.services.cache.storage.memory import MemoryStorage
from app.services.cache.temporary import TemporaryCacheService
from app.services.instagram import InstagramMedia, InstagramService
from tests.services.test_instagram_responses import (
    API,
    CRAWLER,
    FEED,
    IMAGE,
    POST,
    USER,
    api_profile,
)
from tests.services.test_instagram_responses import (
    instagram_server as _instagram_server,
)

instagram_server = _instagram_server
pytestmark = pytest.mark.integration
SECRET = "sensitive-response-value"


def crawler_page(component, props=None, markup="", objects=()):
    root = {"rootView": {"resource": {"__dr": component}, "props": props or {}}}
    payload = json.dumps([root, *objects])
    return f'<html>{markup}<script type="application/json">{payload}</script></html>'


@pytest.mark.parametrize(
    ("component", "props", "markup", "reason"),
    [
        ("PolarisErrorRoot.react", {"failure_reason": SECRET}, "", "error_page"),
        ("PolarisLoggedOutMobileGatedBlockRoot.react", {}, "", "logged_out_gate"),
        (
            "other",
            {},
            f'<form action="/accounts/login/?next={SECRET}"></form>',
            "login_page",
        ),
        ("other", {}, f'<form action="/challenge/{SECRET}"></form>', "challenge_page"),
        ("other", {"restricted_age": 18}, "", "age_restricted"),
    ],
)
async def test_refusal_cannot_be_mistaken_for_empty_profile(
    instagram_server, component, props, markup, reason
):
    local = instagram_server
    timeline = {"id": "123", "polaris_timeline_connection": {"count": 0, "edges": []}}
    local.respond(CRAWLER, crawler_page(component, props, markup, [USER, timeline]))

    with capture_logs() as logs, pytest.raises(FeedUnavailable) as raised:
        await local.service.get_media()

    assert raised.value.reason == "profile_unavailable"
    failure = next(log for log in logs if log.get("source") == "crawler")
    assert failure["reason"] == reason
    assert failure["matching_profiles"] == 1
    assert failure["timeline_objects"] == 1
    assert local.requests[API] == local.requests[FEED] == 1
    assert SECRET not in json.dumps(logs)


async def test_refused_page_still_falls_back_to_valid_api(instagram_server):
    local = instagram_server
    local.respond(CRAWLER, crawler_page("PolarisErrorRoot.react", objects=[USER]))
    local.respond(API, api_profile([POST]))

    with capture_logs() as logs:
        media = await local.service.get_media()

    assert media == [InstagramMedia(IMAGE, f"{local.base_url}/p/Ab_1/")]
    assert any(log.get("reason") == "error_page" for log in logs)


async def test_login_link_on_profile_is_not_a_refusal(instagram_server):
    local = instagram_server
    timeline = {"id": "123", "polaris_timeline_connection": {"count": 0, "edges": []}}
    local.respond(
        CRAWLER,
        crawler_page(
            "PolarisProfilePostsLoggedOutTabGridRoot.react",
            markup='<a href="/accounts/login/">Log in</a>',
            objects=[USER, timeline],
        ),
    )

    assert await local.service.get_media() == []
    assert local.requests[API] == 0


async def test_partial_profiles_report_safe_evidence(instagram_server):
    local = instagram_server
    local.respond(
        CRAWLER,
        crawler_page(
            SECRET,
            objects=[{"username": "example"}, {"username": "example", "id": "123"}],
        ),
    )

    with capture_logs() as logs, pytest.raises(FeedUnavailable):
        await local.service.get_media()

    failure = next(log for log in logs if log.get("source") == "crawler")
    assert failure["reason"] == "missing_profile"
    assert failure["matching_username_objects"] == 2
    assert failure["matching_id_profiles"] == 1
    assert failure["matching_privacy_profiles"] == 0
    assert failure["page_state"] == "unknown"
    assert SECRET not in json.dumps(logs)


async def test_expired_cooldown_allows_request_and_remains_observable(instagram_server):
    local = instagram_server
    cache = TemporaryCacheService[bytes](MemoryStorage())
    cache.set_with_expiry(
        "instagram:profile-api:rate-limited", b"1", timedelta(seconds=-1)
    )
    local.respond(API, api_profile([POST]))

    with capture_logs() as logs:
        media = await InstagramService("example", cache).get_media()

    assert media == [InstagramMedia(IMAGE, f"{local.base_url}/p/Ab_1/")]
    event = next(log for log in logs if log.get("event") == "instagram_profile_fetched")
    assert event["rate_limit_cooldown_state"] == "expired"
    assert event["authentication_cooldown_state"] == "missing"
    assert local.requests[API] == 1


async def test_active_cooldown_skips_only_affected_source(instagram_server):
    local = instagram_server
    cache = TemporaryCacheService[bytes](MemoryStorage())
    cache.set_with_expiry(
        "instagram:profile-api:rate-limited", b"1", timedelta(minutes=2)
    )
    local.respond(FEED, {"user": USER, "items": [POST]})

    with capture_logs() as logs:
        media = await InstagramService("example", cache).get_media()

    assert media == [InstagramMedia(IMAGE, f"{local.base_url}/p/Ab_1/")]
    event = next(log for log in logs if log.get("event") == "instagram_api_skipped")
    assert event["source"] == "profile-api"
    assert event["rate_limit_cooldown_state"] == "active"
    assert event["cooldown_remaining_seconds"] > 0
    assert local.requests[API] == 0
    assert local.requests[FEED] == 1
