import pytest
from aiohttp import web
from structlog.testing import capture_logs

from app.extensions.parsers.exceptions import FeedUnavailable
from app.parsers.reddit import RedditFeed
from app.serializers.feed import Feed

POST_PAGE = """
<div id="posts"><div class="post">
  <h2 class="post_title">A Reddit post</h2>
  <div class="post_body"><p>Post body</p></div>
  <span class="created" title="2026-10-01T12:00:00Z"></span>
  <a class="post_comments" href="/r/neovim/comments/abc/post">Comments</a>
</div></div>
"""
EMPTY_PAGE = """
<main><div id="column_one">
  <center>No posts were found.</center><div id="posts"></div>
</div></main>
"""
ERROR_PAGES = [
    ('<div id="error"><h1>Upstream failed</h1></div>', "reddit_mirror_error_page"),
    ('<form id="challenge-form">Verify your browser</form>', "reddit_mirror_challenge"),
    ("<html><body>Unexpected page</body></html>", "invalid_page"),
    ('<div id="posts"></div>', "invalid_page"),
]


@pytest.fixture
async def mirror_server(tmp_path, monkeypatch, unused_tcp_port):
    # Keep the real URLRanker's persisted data out of the working copy.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    pages = {}
    requests = []

    async def handle(request):
        mirror = request.match_info["mirror"]
        requests.append(mirror)
        if mirror == "redirect-loop":
            raise web.HTTPFound(location=str(request.rel_url))
        return web.Response(text=pages[mirror], content_type="text/html")

    app = web.Application()
    app.router.add_get("/{mirror}/r/neovim", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", unused_tcp_port)
    await site.start()
    try:
        yield f"http://127.0.0.1:{unused_tcp_port}", pages, requests
    finally:
        await runner.cleanup()


def local_feed(base_urls):
    class LocalRedditFeed(RedditFeed):
        async def _get_base_urls(self):
            return base_urls

    feed = Feed(
        id=1, title="Reddit", type="reddit", url="https://www.reddit.com/r/neovim"
    )
    return LocalRedditFeed(feed, {})


@pytest.mark.parametrize(("page", "reason"), ERROR_PAGES)
async def test_reddit_uses_next_mirror_and_preserves_items(mirror_server, page, reason):
    base_url, pages, requests = mirror_server
    pages.update(failed=page, working=POST_PAGE)
    parser = local_feed([f"{base_url}/failed", f"{base_url}/working"])

    with capture_logs() as logs:
        items = await parser.apply_hashes(await parser.items)

    assert requests == ["failed", "working"]
    assert len(items) == 1
    item = items[0]
    assert item.title == "A Reddit post"
    assert item.text == "Post body<br/><br/>r/neovim"
    assert item.link == "https://www.reddit.com/r/neovim/comments/abc/post"
    assert item.date.isoformat() == "2026-10-01T12:00:00+00:00"
    assert item.hash
    assert any(log.get("reason") == reason for log in logs)
    cached_items = await parser.apply_hashes(await parser.items)
    assert cached_items == items
    assert requests == ["failed", "working"]


@pytest.mark.parametrize(("page", "reason"), ERROR_PAGES)
async def test_reddit_exhausted_mirrors_report_failure(mirror_server, page, reason):
    base_url, pages, requests = mirror_server
    pages.update(first=page, second=page)
    parser = local_feed([f"{base_url}/first", f"{base_url}/second"])

    with pytest.raises(FeedUnavailable) as caught:
        await parser.items

    assert requests == ["first", "second"]
    assert caught.value.url == parser.feed.url
    assert caught.value.reason == f"reddit_mirrors_exhausted:{reason}"
    cause = caught.value.__cause__
    if reason == "invalid_page":
        assert isinstance(cause, ValueError)
        assert "neither posts nor a confirmed empty listing" in str(cause)
    else:
        assert isinstance(cause, FeedUnavailable)
        assert cause.reason == reason


async def test_reddit_confirmed_empty_listing_is_success(mirror_server):
    base_url, pages, requests = mirror_server
    pages.update(empty=EMPTY_PAGE, working=POST_PAGE)
    parser = local_feed([f"{base_url}/empty", f"{base_url}/working"])

    assert await parser.items == []
    assert requests == ["empty"]


async def test_reddit_network_error_uses_next_mirror(mirror_server):
    base_url, pages, requests = mirror_server
    pages["working"] = POST_PAGE
    parser = local_feed([f"{base_url}/redirect-loop", f"{base_url}/working"])

    assert len(await parser.items) == 1
    assert requests[-1] == "working"
    assert "redirect-loop" in requests


async def test_reddit_network_exhaustion_preserves_cause(mirror_server):
    base_url, _, _ = mirror_server
    parser = local_feed([f"{base_url}/redirect-loop"])

    with pytest.raises(FeedUnavailable) as caught:
        await parser.items

    assert caught.value.reason == "reddit_mirrors_exhausted:http_request_failed"
    assert isinstance(caught.value.__cause__, FeedUnavailable)
    assert caught.value.__cause__.__cause__ is not None


async def test_reddit_no_available_mirrors_is_unavailable():
    with pytest.raises(FeedUnavailable, match="no_mirrors_available"):
        await local_feed([]).items
