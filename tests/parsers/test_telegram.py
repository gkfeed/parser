import pytest

from app.parsers.telegram import TelegramFeed

from . import fetch_items  # noqa: F401


@pytest.mark.parametrize(
    "fetch_items",
    [{"type": "telegram", "parser": TelegramFeed, "url": "https://t.me/mudotalida"}],
    indirect=True,
)
async def test_telegram_feed(fetch_items):  # noqa: F811
    assert fetch_items
    assert all(item.link.startswith("https://t.me/mudotalida/") for item in fetch_items)
    assert all(item.date.tzinfo is not None for item in fetch_items)
    assert len({item.link for item in fetch_items}) == len(fetch_items)
