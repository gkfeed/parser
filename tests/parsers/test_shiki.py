import pytest
from app.parsers.shiki import ShikiFeed
from app.serializers.feed import Feed
from . import fetch_items  # noqa
from app.extensions.parsers.hash import ItemsHashExtension


SHIKI_FEED_DATA = [
    {
        "type": "shiki",
        "parser": ShikiFeed,
        "url": "https://shikimori.one/animes/51180",
    },
    {
        "type": "shiki",
        "parser": ShikiFeed,
        "url": "https://shikimori.me/animes/57616",
    },
]


@pytest.mark.parametrize("fetch_items", SHIKI_FEED_DATA, indirect=True)
async def test_shiki_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) != 0


@pytest.mark.parametrize("fetch_items", SHIKI_FEED_DATA[:1], indirect=True)
async def test_shiki_feed_hashing(fetch_items):  # noqa: F811
    feed = Feed(id=1, title="shiki", type="shiki", url=SHIKI_FEED_DATA[0]["url"])
    parser = ShikiFeed(feed, {})
    assert isinstance(parser, ItemsHashExtension)

    items = await parser.apply_hashes(fetch_items)
    for item in items:
        assert item.hash is not None
