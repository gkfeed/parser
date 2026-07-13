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
    html = requests.get("https://ranobe.me/news", timeout=20).content
    soup = BeautifulSoup(html, "html.parser")
    for title_link in soup.select(".FicTable_Title a[href]"):
        card = title_link.parent.parent
        chapter_link = card.select_one(".news_chapters_list a[href]")
        if chapter_link is None:
            continue
        chapter_response = requests.get(
            "https://ranobe.me" + chapter_link["href"], timeout=20
        )
        if chapter_response.ok and chapter_response.content:
            return {
                "type": "ranobeme",
                "parser": RanobeMeFeed,
                "url": "https://ranobe.me" + title_link["href"],
            }
    pytest.skip("RanobeMe has no readable recently updated chapters")


@pytest.mark.parametrize("fetch_items", [get_ranobeme_feed_data], indirect=True)
async def test_ranobeme_feed(fetch_items):  # noqa: F811
    assert len(fetch_items) != 0
