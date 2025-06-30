import pytest
from app.parsers.onefootball import OneFootballFeed
from . import fetch_items  # noqa

ONEFOOTBALL_FEED_DATA = {
    "type": "onefootball",
    "parser": OneFootballFeed,
    "url": "https://onefootball.com/en/team/barcelona-5",
}


@pytest.mark.parametrize("fetch_items", [ONEFOOTBALL_FEED_DATA], indirect=True)
async def test_onefootball_feed(fetch_items):  # noqa: F811
    items = await fetch_items
    assert len(items) != 0
    # test if parser works correctly it must return only 2 items
    assert len(items) == 2
