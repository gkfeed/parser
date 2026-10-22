from html import escape
from typing import Literal
from xml.etree import ElementTree

from app.extensions.parsers.exceptions import FeedUnavailable
from app.serializers.feed import Item
from app.services.http import HttpRequestError, HttpService
from app.utils.datetime import parse_datetime

ContentSource = Literal["description", "encoded", "enclosure"]
CONTENT_ENCODED = "{http://purl.org/rss/1.0/modules/content/}encoded"


def _text(element: ElementTree.Element, name: str, default: str = "") -> str:
    child = element.find(name)
    return default if child is None else "".join(child.itertext())


def _description(
    element: ElementTree.Element, priority: tuple[ContentSource, ...]
) -> str:
    # Accept both the RSS content module and the unqualified encoded variant.
    encoded = next(
        (child for child in element if child.tag in (CONTENT_ENCODED, "encoded")),
        None,
    )
    enclosure = element.find("enclosure")
    enclosure_url = enclosure.get("url", "") if enclosure is not None else ""
    sources = {
        "description": _text(element, "description"),
        "encoded": "".join(encoded.itertext()) if encoded is not None else "",
        # Keep the historical image markup, including for untyped enclosures.
        "enclosure": (
            f'<img src="{escape(enclosure_url, quote=True)}" alt="" />'
            if enclosure_url.strip()
            else ""
        ),
    }
    return next((sources[source] for source in priority if sources[source]), "")


class RSSParser:
    @staticmethod
    async def fetch_bytes(url: str, headers: dict[str, str] | None = None) -> bytes:
        try:
            response = await HttpService.get_response(
                url, headers=HttpService.headers if headers is None else headers
            )
        except HttpRequestError as exc:
            raise FeedUnavailable(url, "http_request_failed") from exc
        if not 200 <= response.status < 300:
            raise FeedUnavailable(url, f"http_status_{response.status}")
        return response.content

    @staticmethod
    async def parse_items(url: str) -> list[Item]:
        return RSSParser.items_from_feed(await RSSParser.parse_feed(url))

    @staticmethod
    def items_from_feed(
        feed: list[dict[str, str]], *, include_guid: bool = True
    ) -> list[Item]:
        return [
            Item(
                title=item["title"],
                link=item["link"],
                text=item["description"],
                date=parse_datetime(item["pub_date"]),
                guid=item.get("guid", "") if include_guid else None,
            )
            for item in feed
        ]

    @staticmethod
    async def parse_feed(url: str) -> list[dict[str, str]]:
        return RSSParser.parse_bytes(await RSSParser.fetch_bytes(url))

    @staticmethod
    def parse_bytes(
        content: bytes,
        *,
        content_priority: tuple[ContentSource, ...] = (
            "description",
            "encoded",
            "enclosure",
        ),
        default_title: str = "",
    ) -> list[dict[str, str]]:
        """Parse RSS without fetching it; content priorities belong to the caller.

        Web prefers description. Sasflix supplies encoded/enclosure/description
        to preserve its existing image fallback. CDATA/escaped HTML stays intact.
        """
        try:
            root = ElementTree.fromstring(content)
        except (ElementTree.ParseError, LookupError, ValueError) as exc:
            raise ValueError(f"Invalid RSS XML: {exc}") from exc

        channels = root.findall("channel")
        if root.tag != "rss" or len(channels) != 1:
            raise ValueError("Expected an RSS document with one channel")

        items = []
        for index, element in enumerate(channels[0].findall("item"), start=1):
            item = {
                "title": _text(element, "title", default_title),
                "link": _text(element, "link"),
                "description": _description(element, content_priority),
                "pub_date": _text(element, "pubDate"),
                "guid": _text(element, "guid"),
            }
            for field in ("title", "link", "pub_date"):
                if not item[field].strip():
                    raise ValueError(f"RSS item {index}: missing or empty {field}")
            try:
                parse_datetime(item["pub_date"])
            except (ValueError, OverflowError) as exc:
                raise ValueError(f"RSS item {index}: invalid pubDate: {exc}") from exc
            items.append(item)
        return items
