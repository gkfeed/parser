import json
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest
from aiohttp import web

from app.parsers.liquidpedia import LiquidpediaFeed
from app.serializers.feed import Feed

MATCH_HTML = """
<h2><span id="Upcoming_Matches">Upcoming Matches</span></h2>
<div>
  <div class="match-info" data-timestamp="1700000000">
    <div class="match-info-opponent-row"><span class="name">Team Spirit</span></div>
    <div class="match-info-opponent-row"><span class="name">Team Liquid</span></div>
    <a href="/dota2/Match:Fixture">Match</a>
  </div>
</div>
"""
EMPTY_TEAM_HTML = """
<div data-infobox-type="Team"><div class="infobox-header">Team Spirit</div></div>
"""


@pytest.mark.parametrize("legacy", [False, True], ids=["formatversion2", "legacy"])
@pytest.mark.parametrize("page", ["Team_Spirit", "index.php?title=Team_Spirit"])
async def test_api_payload_becomes_match_items(parser_site, legacy, page):
    text = {"*": MATCH_HTML} if legacy else MATCH_HTML
    parser_site.pages["/dota2/api.php"] = web.json_response({"parse": {"text": text}})
    feed = Feed(
        id=1,
        title="Team Spirit",
        type="liquidpedia",
        url=f"{parser_site.url}/dota2/{page}",
    )

    items = await LiquidpediaFeed(feed, {}).items

    assert len(items) == 1
    assert items[0].title == "Team Spirit vs Team Liquid"
    assert items[0].text == "Team Spirit vs Team Liquid"
    assert items[0].link == f"{parser_site.url}/dota2/Match:Fixture"
    assert items[0].date == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)
    assert len(parser_site.requests) == 1
    request = urlsplit(parser_site.requests[0])
    assert request.path == "/dota2/api.php"
    assert parse_qs(request.query) == {
        "action": ["parse"],
        "page": ["Team_Spirit"],
        "prop": ["text"],
        "format": ["json"],
        "formatversion": ["2"],
    }


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        json.dumps({"error": {"code": "missingtitle"}}).encode(),
        json.dumps({"parse": {"text": {}}}).encode(),
        json.dumps({"parse": {"text": "<html>Access denied</html>"}}).encode(),
    ],
    ids=["invalid-json", "api-error", "missing-html", "invalid-page"],
)
async def test_invalid_api_payload_raises_instead_of_returning_empty(parser_site, body):
    parser_site.pages["/dota2/api.php"] = web.Response(body=body)
    feed = Feed(
        id=1,
        title="Team",
        type="liquidpedia",
        url=f"{parser_site.url}/dota2/Team_Spirit",
    )

    with pytest.raises(ValueError):
        await LiquidpediaFeed(feed, {}).items


async def test_verified_team_without_matches_returns_empty(parser_site):
    parser_site.pages["/dota2/api.php"] = web.json_response(
        {"parse": {"text": EMPTY_TEAM_HTML}}
    )
    feed = Feed(
        id=1,
        title="Team",
        type="liquidpedia",
        url=f"{parser_site.url}/dota2/Team_Spirit",
    )

    assert await LiquidpediaFeed(feed, {}).items == []
