import json
from datetime import UTC, datetime, timedelta

import pytest
from selenium.common.exceptions import TimeoutException
from structlog.testing import capture_logs

from app.extensions.parsers.exceptions import FeedUnavailable
from app.services.selenium.lazy_list import (
    LazyListTimeoutError,
    LazyListUnavailableError,
)
from tests.browser.stories import FORM, media, result, stories_parser

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    ("status", "body", "reason", "stage"),
    [
        (
            503,
            "<title>Service unavailable</title>",
            "upstream_http_error",
            "search_form",
        ),
        (
            403,
            "<title>Verify you are human</title>",
            "challenge_required",
            "search_form",
        ),
        (429, "<title>Too many requests</title>", "rate_limited", "search_form"),
        (401, "<title>Unauthorized</title>", "authentication_required", "search_form"),
        (200, "<title>Log in</title>", "authentication_required", "search_form"),
        (200, "<title>HTTP Error 503</title>", "upstream_http_error", "search_form"),
        (200, "", "search_form_timeout", "search_form"),
        (200, "No stories for the last 24 hours", "search_form_timeout", "search_form"),
        (200, FORM, "search_result_timeout", "search_result"),
        (
            200,
            result('<button class="tabs-component__button">Stories</button>'),
            "stories_media_timeout",
            "stories_media",
        ),
        (
            200,
            result('<button class="tabs-component__button" disabled>Stories</button>'),
            "stories_tab_disabled",
            "stories_tab",
        ),
    ],
)
async def test_stories_refusals_and_unverified_pages_fail(
    site, browser, status, body, reason, stage
):
    parser = stories_parser(site.publish(body, status=status), browser)
    started = datetime.now(UTC)

    with capture_logs() as logs, pytest.raises(FeedUnavailable) as raised:
        await parser.items

    assert raised.value.reason == reason
    assert raised.value.url == parser.feed.url
    assert raised.value.retry_at is not None
    assert (
        started + timedelta(minutes=1)
        <= raised.value.retry_at
        <= datetime.now(UTC) + timedelta(minutes=1)
    )
    if stage != "stories_tab":
        assert isinstance(raised.value.__cause__, TimeoutException)
    assert len(logs) == 1
    assert logs[0]["event"] == "stories_source_unavailable"
    assert logs[0]["reason"] == reason
    assert logs[0]["stage"] == stage
    assert logs[0]["document_status"] == status
    browser.assert_released()


@pytest.mark.parametrize(
    ("message", "reason", "delay"),
    [
        ("Error: 429", "rate_limited", timedelta(minutes=1)),
        ("This account is private", "private", timedelta(days=1)),
        ("User not found", "not_found", timedelta(days=1)),
        ("No stories for the last 24 hours", "empty_unverified", timedelta(minutes=1)),
        ("Unknown source response", "upstream_error", timedelta(minutes=1)),
    ],
)
async def test_stories_classification_context_visibility_and_retry(
    site, browser, message, reason, delay
):
    body = result(
        '<div class="profile-media-list"><i class="trigger">More</i>'
        '<i class="trigger" hidden>Hidden</i></div>'
        f'<div class="error-message__text">{message}</div>'
    )
    parser = stories_parser(site.publish(body), browser)
    started = datetime.now(UTC)

    with capture_logs() as logs, pytest.raises(FeedUnavailable) as raised:
        await parser.items

    assert raised.value.reason == reason
    assert raised.value.retry_at is not None
    assert started + delay <= raised.value.retry_at <= datetime.now(UTC) + delay
    assert len(logs) == 1
    event = logs[0]
    assert event["event"] == "stories_source_unavailable"
    assert event["reason"] == reason
    assert event["stage"] == "search_result"
    assert event["search_forms"] == 1
    assert event["search_results"] == 1
    assert event["pagination_triggers"] == 2
    assert event["visible_pagination_triggers"] == 1
    browser.assert_released()


@pytest.mark.parametrize("location", ["source", "page"])
async def test_stories_diagnostics_do_not_leak_html_or_credentials(
    site, browser, location
):
    url = site.url + "/?token=SECRET_MARKER"
    body = f"Failed SECRET_MARKER {url} &lt;html&gt;"
    if location == "source":
        body = result(f'<div class="error-message__text">{body}</div>')
    site.publish(body)
    parser = stories_parser(url, browser)

    with capture_logs() as logs, pytest.raises(FeedUnavailable):
        await parser.items

    assert len(logs) == 1
    assert logs[0]["message_hash"]
    assert logs[0]["message_length"] > 0
    serialized = json.dumps(logs)
    for forbidden in (
        "SECRET_MARKER",
        "<html",
        "&lt;html",
        "token=",
        site.url,
        "source_message",
        "page_message",
    ):
        assert forbidden not in serialized
    assert "/?token=SECRET_MARKER" in site.requests
    browser.assert_released()


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        (None, None),
        (
            result('<div class="error-message__text">This account is private</div>'),
            "private",
        ),
        ("", "search_form_timeout"),
    ],
)
async def test_stories_parser_reuse_after_success_error_or_timeout(
    site, browser, body, reason
):
    url = site.publish(media(site.url) if body is None else body)
    parser = stories_parser(url, browser)
    parser._results_wait_time = 4 if reason is None else 0
    if reason is None:
        assert b"download-btn" in await parser.get_html(url)
    else:
        with pytest.raises(FeedUnavailable) as raised:
            await parser.items
        assert raised.value.reason == reason
    browser.assert_released()

    site.publish(media(site.url))
    parser._results_wait_time = 4
    with capture_logs() as logs:
        html = await parser.get_html(url)

    assert b"download-btn" in html
    assert (site.url + "/video.mp4").encode() in html
    assert logs == []
    assert len(browser.drivers) == 2
    assert site.requests.count("/") == 2
    browser.assert_released()
    with pytest.raises(RuntimeError, match="Browser actions are not active"):
        _ = parser.driver


@pytest.mark.parametrize(
    ("trigger", "script", "reason", "cause"),
    [
        ("", "", "media_loading_unverified", LazyListUnavailableError),
        (
            '<div class="trigger" hidden>More</div>',
            "",
            "media_loading_unverified",
            LazyListUnavailableError,
        ),
        (
            '<div class="trigger">More</div>',
            "<script>setInterval(() => document.querySelector('.profile-media-list').insertAdjacentHTML('afterbegin', '<i class=profile-media-list__item></i>'), 100)</script>",
            "media_loading_timeout",
            LazyListTimeoutError,
        ),
    ],
)
async def test_stories_rejects_unverified_or_endless_pagination(
    site, browser, trigger, script, reason, cause
):
    url = site.publish(media(site.url, trigger=trigger) + script)
    parser = stories_parser(url, browser)
    parser._results_wait_time = 1

    with capture_logs() as logs, pytest.raises(FeedUnavailable) as raised:
        await parser.get_html(url)

    assert raised.value.reason == reason
    assert isinstance(raised.value.__cause__, cause)
    assert logs[0]["stage"] == "pagination"
    assert logs[0]["reason"] == reason
    browser.assert_released()
