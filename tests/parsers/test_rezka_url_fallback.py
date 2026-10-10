import pytest

from app.parsers.rezka import RezkaFeed

from . import fetch_items  # noqa

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    ("fetch_items", "expected_url", "title"),
    [
        (
            {
                "type": "rezka",
                "parser": RezkaFeed,
                "url": "https://hdrezka.me/series/comedy/63817-prazdniki-2023.html",
            },
            "https://hdrezka.me/series/comedy/63817-prazdniki-serial-2023-latest.html",
            "Праздники (сериал)",
        ),
        (
            {
                "type": "rezka",
                "parser": RezkaFeed,
                "url": "https://hdrezka.me/series/drama/87371-na-ldu-2026.html",
            },
            "https://hdrezka.me/series/drama/87371-na-ldu-2026-u.html",
            "На льду",
        ),
        (
            {
                "type": "rezka",
                "parser": RezkaFeed,
                "url": "https://hdrezka.me/series/comedy/90878-sueta-2026.html?source=feed#episodes",
            },
            "https://hdrezka.me/series/comedy/90878-sueta-2026-u.html?source=feed#episodes",
            "Суета",
        ),
        (
            {
                "type": "rezka",
                "parser": RezkaFeed,
                "url": "https://hdrezka.me/series/drama/87371-na-ldu-2026-latest.html",
            },
            "https://hdrezka.me/series/drama/87371-na-ldu-2026-u.html",
            "На льду",
        ),
    ],
    indirect=["fetch_items"],
)
async def test_rezka_resolves_changed_show_urls(fetch_items, expected_url, title):  # noqa: F811
    assert fetch_items
    assert all(item.title.startswith(title + " ") for item in fetch_items)
    assert all(item.link == expected_url for item in fetch_items)
