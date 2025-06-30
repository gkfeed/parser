import requests
from bs4 import BeautifulSoup

import pytest
from app.parsers.ranobeme import RanobeMeFeed
from . import fetch_items  # noqa

RANOBEME_FEED_DATA = {
    "type": "ranobeme",
    "parser": RanobeMeFeed,
    "url": "https://ranobe.me/ranobe24",
}


def get_ranobeme_feed_data():
    html = requests.get("https://ranobe.me/news").content
    soup = BeautifulSoup(html, "html.parser")
    new_updated_ranobe_link = "https://ranobe.me" + soup.find_all("a")[14]["href"]
    return {
        "type": "ranobeme",
        "parser": RanobeMeFeed,
        "url": new_updated_ranobe_link,
    }


@pytest.mark.parametrize("fetch_items", [get_ranobeme_feed_data()], indirect=True)
async def test_ranobeme_feed(fetch_items):  # noqa: F811
    assert len(await fetch_items) != 0
