import pytest
from app.parsers.pornhub import PornHubFeed
from . import fetch_items  # noqa


PORNHUB_FEEDS = [
    {
        "type": "pornhub",
        "parser": PornHubFeed,
        "url": "https://www.pornhub.com/pornstar/jewelz-blu",
    },
    {
        "type": "pornhub",
        "parser": PornHubFeed,
        "url": "https://de.pornhub.org/model/nolube",
    },
]


@pytest.mark.parametrize("fetch_items", PORNHUB_FEEDS, indirect=True)
async def test_pornhub_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) > 0
