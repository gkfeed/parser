import pytest
from app.parsers.liveball import LiveballFeed
from . import fetch_items  # noqa

LIVEBALL_FEED_DATA = {
    "type": "liveball",
    "parser": LiveballFeed,
    "url": "https://liveball.sx/",
}


@pytest.mark.parametrize("fetch_items", [LIVEBALL_FEED_DATA], indirect=True)
async def test_matreshka_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) != 0
