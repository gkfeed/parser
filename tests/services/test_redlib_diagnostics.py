import asyncio
from collections import Counter
from datetime import UTC, datetime

import pytest
from aiohttp import web
from structlog.testing import capture_logs

from app.extensions.parsers.exceptions import FeedUnavailable
from app.parsers.reddit import RedditFeed
from app.serializers.feed import Feed
from app.services.http import HttpService
from app.services.redlib import RedlibClient
from app.services.url_ranker import URLRanker

pytestmark = pytest.mark.integration

EMPTY = (
    b"<html><div id='column_one'><center>No posts were found.</center>"
    b"<div id='posts'></div></div></html>"
)
POSTS = b"<html><div id='posts'><div class='post'>Post</div></div></html>"
PAGE_URL = "https://www.reddit.com/r/neovim"


@pytest.fixture
async def redlib_server(tmp_path):
    mirrors = []
    pages = {}
    requests = Counter()

    async def directory(request):
        requests[request.path] += 1
        return web.json_response({"instances": [{"url": url} for url in mirrors]})

    async def listing(request):
        requests[request.path] += 1
        status, body = pages[request.match_info["mirror"]]
        return web.Response(status=status, body=body, content_type="text/html")

    app = web.Application()
    app.router.add_get("/instances", directory)
    app.router.add_get("/{mirror}/r/neovim", listing)
    runner = web.AppRunner(app)
    await runner.setup()
    assert runner.server is not None
    server = await asyncio.get_running_loop().create_server(
        runner.server, "127.0.0.1", 0
    )
    base_url = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
    parser = RedditFeed(Feed(id=1, title="Reddit", type="reddit", url=PAGE_URL), {})

    async def fetch_instances(url):
        return await HttpService.get(base_url + "/instances")

    ranker = URLRanker(str(tmp_path / "ranks.json"))
    client = RedlibClient(
        parser.get_html, fetch_instances=fetch_instances, url_ranker=ranker
    )
    try:
        yield base_url, mirrors, pages, requests, client, parser, ranker
    finally:
        server.close()
        await server.wait_closed()
        await runner.cleanup()


@pytest.mark.parametrize(
    ("status", "body", "reason"),
    [
        (403, b"Forbidden", "http_status"),
        (429, b"Rate limited", "http_status"),
        (200, b"<script id='anubis_challenge'>{}</script>", "reddit_mirror_challenge"),
        (200, b"<title>Checking you are not a bot</title>", "reddit_mirror_challenge"),
        (200, b"<form><input type='password'></form>", "reddit_mirror_login"),
        (200, b"<title>Access denied</title>", "reddit_mirror_blocked"),
        (200, b"<html>Unexpected page</html>", "invalid_page"),
        (200, b"<div id='posts'></div>", "invalid_page"),
    ],
)
async def test_mirror_failures_are_classified_before_fallback_and_caching(
    redlib_server, status, body, reason
):
    base_url, mirrors, pages, requests, client, parser, _ = redlib_server
    mirrors.extend([base_url + "/bad", base_url + "/good"])
    pages.update(bad=(status, body), good=(200, POSTS))

    with capture_logs() as logs:
        assert await client.get_page_html(PAGE_URL) == POSTS

    failed = [row for row in logs if row["event"] == "reddit_mirror_failed"]
    assert len(failed) == 1
    assert failed[0]["reason"] == reason
    assert failed[0]["attempt"] == 1
    assert failed[0]["http_status"] == (status if status >= 400 else None)
    assert not parser.cache.has_valid_cache(base_url + "/bad/r/neovim")
    assert parser.cache.has_valid_cache(base_url + "/good/r/neovim")
    assert requests["/bad/r/neovim"] == requests["/good/r/neovim"] == 1

    # Reusing a client must re-evaluate cooldown, rather than retry the cached order.
    assert await client.get_page_html(PAGE_URL) == POSTS
    assert requests["/bad/r/neovim"] == 1
    assert requests["/instances"] == 1


async def test_exhaustion_reports_mixed_failures_and_then_cooldown(redlib_server):
    base_url, mirrors, pages, requests, client, _, ranker = redlib_server
    mirrors.extend([base_url + "/http", base_url + "/challenge"])
    pages.update(
        http=(503, b"Unavailable"), challenge=(200, b"<div id='challenge-form'>")
    )

    with capture_logs() as logs, pytest.raises(FeedUnavailable) as raised:
        await client.get_page_html(PAGE_URL)

    assert raised.value.reason == "reddit_mirrors_exhausted:reddit_mirror_challenge"
    assert raised.value.__cause__ is not None
    assert raised.value.retry_at is not None
    assert raised.value.retry_at > datetime.now(UTC)
    summary = logs[-1]
    assert summary["event"] == "reddit_mirrors_exhausted"
    assert summary["mirrors_configured"] == summary["mirrors_attempted"] == 2
    assert summary["failure_counts"] == {"http_status": 1, "reddit_mirror_challenge": 1}
    assert [row["attempt"] for row in logs[:-1]] == [1, 2]

    with capture_logs() as logs, pytest.raises(FeedUnavailable) as cooled:
        await client.get_page_html(PAGE_URL)

    assert cooled.value.reason == "reddit_mirrors_exhausted:mirrors_on_cooldown"
    assert cooled.value.retry_at == raised.value.retry_at
    assert len(logs) == 1
    assert logs[0]["mirrors_cooling_down"] == 2
    assert logs[0]["mirrors_available"] == logs[0]["mirrors_attempted"] == 0
    assert requests["/http/r/neovim"] == requests["/challenge/r/neovim"] == 1

    # Expired cooldown makes mirrors eligible again, including on a reused client.
    ranker.cooldown_minutes = 0
    pages["http"] = (200, EMPTY)
    assert await client.get_page_html(PAGE_URL) == EMPTY


async def test_empty_directory_is_not_a_successful_empty_feed(redlib_server):
    _, _, _, requests, client, _, _ = redlib_server
    with capture_logs() as logs, pytest.raises(FeedUnavailable) as raised:
        await client.get_page_html(PAGE_URL)

    assert raised.value.reason == "reddit_mirrors_exhausted:no_mirrors_configured"
    assert raised.value.retry_at is None
    assert logs[-1]["mirrors_configured"] == logs[-1]["mirrors_attempted"] == 0
    assert requests == {"/instances": 1}


async def test_only_confirmed_empty_listing_is_accepted_and_cached(redlib_server):
    base_url, mirrors, pages, requests, client, parser, _ = redlib_server
    mirrors.append(base_url + "/empty")
    pages["empty"] = (200, EMPTY)
    with capture_logs() as logs:
        assert await client.get_page_html(PAGE_URL) == EMPTY
        assert await client.get_page_html(PAGE_URL) == EMPTY
    assert not logs
    assert requests["/empty/r/neovim"] == 1
    assert parser.cache.has_valid_cache(base_url + "/empty/r/neovim")


@pytest.mark.parametrize("failure", ["dns_error", "tls_error"])
async def test_real_transport_failures_keep_their_cause(redlib_server, failure):
    base_url, mirrors, _, _, client, _, _ = redlib_server
    mirror = (
        "http://redlib.invalid"
        if failure == "dns_error"
        else base_url.replace("http:", "https:")
    )
    mirrors.append(mirror)

    with capture_logs() as logs, pytest.raises(FeedUnavailable) as raised:
        await client.get_page_html(PAGE_URL)

    assert raised.value.reason == f"reddit_mirrors_exhausted:{failure}"
    assert logs[0]["reason"] == failure
    assert logs[0]["cause_type"]
    assert logs[0]["http_status"] is None
