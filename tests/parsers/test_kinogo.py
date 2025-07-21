import pytest
from app.parsers.kinogo import KinogoFeed
from . import fetch_items  # noqa

KINOGO_FEED_DATA = {
    "type": "kinogo",
    "parser": KinogoFeed,
    "url": "https://kinogo.fm/631-.html",
}


@pytest.mark.parametrize("fetch_items", [KINOGO_FEED_DATA], indirect=True)
async def test_kinogo_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) != 0
