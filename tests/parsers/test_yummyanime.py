import pytest
from app.parsers.yummyanime import YummyAnimeFeed
from . import fetch_items  # noqa

YUMMYANIME_FEED_DATA = {
    "type": "yummyanime",
    "parser": YummyAnimeFeed,
    "url": "https://yummy-anime.org/4769-dobro-pozhalovat-v-klass-prevoshodstva-3.html",
}


@pytest.mark.parametrize("fetch_items", [YUMMYANIME_FEED_DATA], indirect=True)
async def test_yummyanime_feed(fetch_items):
    assert len(await fetch_items) != 0
