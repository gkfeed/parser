import pytest
from app.parsers.matreshka import MatreshkaFeed
from . import fetch_items  # noqa

MATRESHKA_FEED_DATA = {
    "type": "matreshka",
    "parser": MatreshkaFeed,
    "url": "https://matreshka.tv/channel/HgIgri0SAvQ/internal/videos",
}


@pytest.mark.parametrize("fetch_items", [MATRESHKA_FEED_DATA], indirect=True)
async def test_matreshka_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) != 0
