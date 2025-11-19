import pytest
from app.parsers.pornhub import PornHubFeed
from . import fetch_items  # noqa


PORNHUB_FEED_DATA = {
    "type": "pornhub",
    "parser": PornHubFeed,
    "url": "https://www.pornhub.com/pornstar/jewelz-blu",
}


@pytest.mark.parametrize("fetch_items", [PORNHUB_FEED_DATA], indirect=True)
async def test_pornhub_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) > 0
