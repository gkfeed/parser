from html import escape
from typing import Literal
from xml.etree import ElementTree
from xml.parsers import expat

import structlog

from app.extensions.parsers.exceptions import FeedUnavailable
from app.serializers.feed import Item
from app.services.http import HttpRequestError, HttpService
from app.utils.datetime import parse_datetime
from app.utils.logging import url_log_fields

logger = structlog.get_logger(__name__)
ContentSource = Literal["description", "encoded", "enclosure"]
CONTENT_ENCODED = "{http://purl.org/rss/1.0/modules/content/}encoded"


class RSSParseError(ValueError):
    def __init__(
        self, reason: str, xml_error: ElementTree.ParseError | None = None
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.xml_error_code = xml_error.code if xml_error is not None else None
        self.xml_error = (
            expat.ErrorString(xml_error.code) if xml_error is not None else None
        )
        self.line: int | None
        self.column: int | None
        self.line, self.column = (
            xml_error.position if xml_error is not None else (None, None)
        )


class _DocumentBuilder(ElementTree.TreeBuilder):
    """Remember the root even when strict XML parsing fails later in the body."""

    root_tag: str | None = None

    def start(self, tag: str, attrs: dict[str, str]) -> ElementTree.Element:
        if self.root_tag is None:
            self.root_tag = tag
        return super().start(tag, attrs)

    @property
    def is_html(self) -> bool:
        return (
            self.root_tag is not None
            and self.root_tag.rsplit("}", 1)[-1].lower() == "html"
        )


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
        content = await RSSParser.fetch_bytes(url)
        try:
            return RSSParser.parse_bytes(content)
        except RSSParseError as exc:
            safe_url = url_log_fields(url)
            logger.warning(
                "rss_parse_failed",
                **safe_url,
                reason=exc.reason,
                response_bytes=len(content),
                xml_error_code=exc.xml_error_code,
                xml_error=exc.xml_error,
                xml_line=exc.line,
                xml_column=exc.column,
            )
            raise FeedUnavailable(safe_url["url"], exc.reason) from exc

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
        builder = _DocumentBuilder()
        try:
            root = ElementTree.fromstring(
                content, parser=ElementTree.XMLParser(target=builder)
            )
        except ElementTree.ParseError as exc:
            reason = "rss_invalid_xml"
            if exc.code in (
                expat.errors.codes[expat.errors.XML_ERROR_UNKNOWN_ENCODING],
                expat.errors.codes[expat.errors.XML_ERROR_INCORRECT_ENCODING],
            ):
                reason = "rss_invalid_encoding"
            if builder.is_html:
                reason = "rss_html_response"
            raise RSSParseError(reason, exc) from exc
        except (LookupError, ValueError) as exc:
            raise RSSParseError("rss_invalid_encoding") from exc

        if builder.is_html:
            raise RSSParseError("rss_html_response")
        channels = root.findall("channel")
        if root.tag != "rss" or len(channels) != 1:
            raise RSSParseError("rss_invalid_document")

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
