import pytest

from app.parsers.porno365 import Porno365Feed
from app.serializers.feed import Feed, Item
from app.services.hash import HashService
from app.utils.datetime import constant_datetime
from . import fetch_items  # noqa


PORNO365_FEEDS = [
    {
        "type": "porno365",
        "parser": Porno365Feed,
        "url": "http://i.porno365.broker",
    },
]


@pytest.mark.parametrize("fetch_items", PORNO365_FEEDS, indirect=True)
async def test_porno365_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) > 0
    assert fetch_items[0].link.startswith("http://i.porno365.broker/movie/")


async def test_porno365_hash_uses_link_only():
    feed = Feed(id=1, title="porno365", type="porno365", url="http://i.porno365.broker")
    parser = Porno365Feed(feed, {})
    item = Item(
        title="title",
        text="text",
        date=constant_datetime,
        link="http://i.porno365.broker/movie/49040",
    )

    assert await parser._generate_hash(item) == HashService.hash_str(item.link)
