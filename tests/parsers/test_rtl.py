import pytest
from app.parsers.rtl import RTLSeriesFeed
from . import fetch_items  # noqa

RTL_FEED_DATA = {
    "type": "rtl",
    "parser": RTLSeriesFeed,
    "url": "https://plus.rtl.de/video-tv/serien/alles-was-zaehlt-146430",
}


@pytest.mark.parametrize("fetch_items", [RTL_FEED_DATA], indirect=True)
async def test_rtl_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) != 0
