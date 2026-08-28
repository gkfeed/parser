import pytest

from app.parsers.hltv import HltvFeed

from . import fetch_items  # noqa

HLTV_FEED_DATA = {
    "type": "hltv",
    "parser": HltvFeed,
    "url": "https://www.hltv.org/team/7020/spirit",
}


@pytest.mark.parametrize("fetch_items", [HLTV_FEED_DATA], indirect=True)
async def test_hltv_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) != 0
