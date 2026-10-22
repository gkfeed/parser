import json

import pytest
from aiohttp import web
from structlog.testing import capture_logs

from app.extensions.parsers.exceptions import FeedUnavailable
from app.parsers.web import WebFeed
from app.serializers.feed import Feed
from app.services.rss import RSSParser

pytestmark = pytest.mark.integration


@pytest.fixture
async def rss_server():
    async def respond(request):
        path = request.path
        if path == "/redirect":
            raise web.HTTPFound("/challenge?token=redirect-secret")
        if path == "/ok":
            return web.Response(body=b"<rss><channel /></rss>")
        if path == "/challenge":
            return web.Response(
                status=403,
                text="<html>body-secret</html>",
                headers={
                    "cf-mitigated": "challenge",
                    "Content-Type": "text/html; private=header-secret",
                    "Set-Cookie": "session=cookie-secret",
                },
            )
        if path == "/challenge-page":
            return web.Response(
                status=403, text='<script src="/cdn-cgi/challenge-platform/test" />'
            )
        if path == "/suspended":
            return web.Response(
                status=403, text="<title>Работа сайта приостановлена</title>"
            )
        if path == "/auth":
            return web.Response(
                status=403, headers={"WWW-Authenticate": 'Basic realm="auth-secret"'}
            )
        if path == "/missing":
            return web.Response(status=404)
        return web.Response(status=403, headers={"Server": "cloudflare"})

    app = web.Application()
    app.router.add_get("/{path:.*}", respond)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    try:
        yield str(runner.addresses[0][0]) + ":" + str(runner.addresses[0][1])
    finally:
        await runner.cleanup()


@pytest.mark.parametrize(
    ("path", "reason", "markers"),
    [
        (
            "challenge",
            "http_status_403_cloudflare_challenge",
            ["cloudflare_challenge_header"],
        ),
        (
            "challenge-page",
            "http_status_403_cloudflare_challenge",
            ["cloudflare_challenge_page"],
        ),
        ("suspended", "http_status_403_hosting_suspended", ["hosting_suspended_page"]),
        ("auth", "http_status_403_auth_required", ["www_authenticate"]),
        ("unknown", "http_status_403", []),
        ("missing", "http_status_404", []),
    ],
)
async def test_rss_http_denials_raise_and_log_observed_signals(
    rss_server, path, reason, markers
):
    url = f"http://{rss_server}/{path}"
    parser = WebFeed(Feed(id=1, title="RSS", type="web", url=url), {})
    with capture_logs() as events, pytest.raises(FeedUnavailable) as raised:
        await parser.items

    assert raised.value.reason == reason
    event = next(event for event in events if event["event"] == "rss_http_unavailable")
    assert event["reason"] == reason
    assert event["block_markers"] == markers
    assert event["http_status"] == (404 if path == "missing" else 403)
    assert event["url"] == event["final_url"] == url
    assert event["redirect_count"] == 0


async def test_rss_redirect_diagnostics_exclude_secrets(rss_server):
    url = f"http://user:userinfo-secret@{rss_server}/redirect?token=query-secret#fragment-secret"
    with capture_logs() as events, pytest.raises(FeedUnavailable) as raised:
        await RSSParser.fetch_bytes(url)

    assert raised.value.reason == "http_status_403_cloudflare_challenge"
    event = next(event for event in events if event["event"] == "rss_http_unavailable")
    assert event["url"] == f"http://{rss_server}/redirect"
    assert event["final_url"] == f"http://{rss_server}/challenge"
    assert event["content_type"] == "text/html"
    assert event["redirect_count"] == 1
    assert event["redirect_statuses"] == [302]
    assert "secret" not in json.dumps(events)


async def test_successful_rss_fetch_keeps_bytes_contract(rss_server):
    with capture_logs() as events:
        content = await RSSParser.fetch_bytes(f"http://{rss_server}/ok")

    assert content == b"<rss><channel /></rss>"
    assert events == []
