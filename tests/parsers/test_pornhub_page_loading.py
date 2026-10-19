from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from app.parsers.pornhub import PornHubFeed
from app.serializers.feed import Feed
from app.services.hash import HashService

pytestmark = pytest.mark.integration

VALID_CARD = '<a class="linkVideoThumb" href="/view_video.php?viewkey=one"><img title="One"></a>'


@pytest.fixture
def pornhub_server():
    pages = {}
    requests = Counter()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests[self.path] += 1
            body = pages.get(self.path, "").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", pages, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def parser_for(url: str) -> PornHubFeed:
    return PornHubFeed(Feed(id=1, title="PornHub", type="pornhub", url=url), {})


async def test_pornhub_preserves_titles_deduplication_and_cached_items(pornhub_server):
    base_url, pages, requests = pornhub_server
    pages["/feed"] = f"""
        <ul id="claimedUploadedVideoSection">
          <li><a href="/help">Help</a></li>
          <li>{VALID_CARD}</li>
          <li><a class="linkVideoThumb" href="/view_video.php?viewkey=two">
            <img title=" " data-title=" Two " alt="Ignored"></a></li>
        </ul>
        <ul id="modelMostRecentVideosSection">
          <li>{VALID_CARD}</li>
          <li><a class="linkVideoThumb" href="/view_video.php?viewkey=three">
            <img title="" data-title=" " alt=" Three "></a></li>
        </ul>
    """
    parser = parser_for(base_url + "/feed")

    items = await parser.apply_hashes(await parser.items)

    assert [item.title for item in items] == ["One", "Two", "Three"]
    assert [item.text for item in items] == ["One", "Two", "Three"]
    assert [item.link for item in items] == [
        f"{base_url}/view_video.php?viewkey={key}" for key in ("one", "two", "three")
    ]
    assert [item.hash for item in items] == [
        HashService.hash_str(item.link) for item in items
    ]
    assert await parser.apply_hashes(await parser.items) == items
    assert requests["/feed"] == 1


@pytest.mark.parametrize(
    ("card", "reason"),
    [
        ('<a class="linkVideoThumb"><img title="Broken"></a>', "href"),
        ('<a class="linkVideoThumb" href><img title="Broken"></a>', "href"),
        ('<a class="linkVideoThumb" href=" "><img title="Broken"></a>', "href"),
        ('<a class="linkVideoThumb" href="/broken"><img></a>', "No title"),
        ('<a class="linkVideoThumb" href="/broken"></a>', "No title"),
        (
            (
                '<a class="linkVideoThumb" href="/broken">'
                '<img title=" " data-title=" " alt=" "></a>'
            ),
            "No title",
        ),
        # A malformed duplicate must also fail instead of hiding the broken card.
        (
            '<a class="linkVideoThumb" href="/view_video.php?viewkey=one"><img></a>',
            "No title",
        ),
    ],
)
@pytest.mark.parametrize("include_valid_card", [False, True])
async def test_pornhub_rejects_damaged_cards_without_partial_results(
    pornhub_server, card, reason, include_valid_card
):
    base_url, pages, _ = pornhub_server
    valid_card = VALID_CARD if include_valid_card else ""
    pages["/feed"] = f'<ul id="uploadedVideosSection">{valid_card}{card}</ul>'

    with pytest.raises(ValueError, match=reason):
        await parser_for(base_url + "/feed").items


@pytest.mark.parametrize(
    "contents",
    [
        "",
        '<li><a href="/help">Help</a></li>',
        '<li><a class="newVideoThumb" href="/video"><img title="Video"></a></li>',
    ],
)
async def test_pornhub_rejects_unrecognized_or_unconfirmed_empty_sections(
    pornhub_server, contents
):
    base_url, pages, _ = pornhub_server
    pages["/feed"] = f'<ul id="mostRecentVideosSection">{contents}</ul>'

    with pytest.raises(ValueError, match="No video cards"):
        await parser_for(base_url + "/feed").items


async def test_pornhub_rejects_missing_video_sections(pornhub_server):
    base_url, pages, _ = pornhub_server
    pages["/feed"] = f'<ul id="replacementSection">{VALID_CARD}</ul>'

    with pytest.raises(ValueError, match="Videosection not found"):
        await parser_for(base_url + "/feed").items
