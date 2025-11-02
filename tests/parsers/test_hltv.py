from unittest.mock import AsyncMock, patch

import pytest
from bs4 import BeautifulSoup

from app.parsers.hltv import HltvFeed
from app.serializers.feed import Feed
from . import fetch_items  # noqa

HLTV_FEED_DATA = {
    "type": "hltv",
    "parser": HltvFeed,
    "url": "https://www.hltv.org/team/7020/spirit",
}


@pytest.mark.parametrize("fetch_items", [HLTV_FEED_DATA], indirect=True)
async def test_hltv_feed(fetch_items):  # noqa: F811
    breakpoint()
    assert len(fetch_items) != 0


async def test_hltv_feed_value_error():
    feed = Feed(
        id=1,
        title="Test Feed",
        url="https://www.hltv.org/team/7020/spirit",
        type="hltv",
    )
    parser = HltvFeed(feed, {})

    with patch.object(parser, "get_soup", new_callable=AsyncMock) as mock_get_soup:
        mock_get_soup.return_value = BeautifulSoup("<html><body></body></html>", "lxml")
        with pytest.raises(ValueError, match="Upcoming matches headline not found."):
            await parser.items
