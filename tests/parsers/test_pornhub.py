import pytest
from app.parsers.pornhub import PornHubFeed
from app.serializers.feed import Feed
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
    {
        "type": "pornhub",
        "parser": PornHubFeed,
        "url": "https://de.pornhub.org/pornstar/aria-valencia",
    },
]


@pytest.mark.parametrize("fetch_items", PORNHUB_FEEDS, indirect=True)
async def test_pornhub_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) > 0


def test_pornhub_pornstar_feed_uses_profile_page():
    feed = Feed(
        id=1,
        title="pornhub",
        type="pornhub",
        url="https://de.pornhub.org/pornstar/aria-valencia",
    )
    parser = PornHubFeed(feed, {})

    assert parser._get_posts_url() == "https://de.pornhub.org/pornstar/aria-valencia"
