from app.parsers.web import WebFeed
from app.serializers.feed import Feed
from app.services.rss import RSSParser


async def test_web_feed_preserves_pub_date_instant(monkeypatch) -> None:
    async def parse_feed(_url: str) -> list[dict[str, str]]:
        return [
            {
                "title": "Timed post",
                "link": "https://example.com/post",
                "description": "Description",
                "pub_date": "Mon, 14 Sep 2026 10:00:00 +0300",
                "guid": "post-1",
            }
        ]

    monkeypatch.setattr(RSSParser, "parse_feed", parse_feed)
    parser = WebFeed(
        Feed(id=1, title="Example", type="web", url="https://example.com/feed"),
        {},
    )

    items = await parser.items

    assert len(items) == 1
    assert items[0].date.isoformat() == "2026-09-14T07:00:00+00:00"
