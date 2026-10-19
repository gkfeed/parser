import json
from collections.abc import Awaitable, Callable
from typing import ClassVar
from urllib.parse import SplitResult, parse_qs, unquote, urlencode, urlsplit, urlunsplit

from app.services.http import HttpService


def get_page_title(url: SplitResult, path_page: str) -> str:
    if path_page.casefold() == "index.php":
        path_page = parse_qs(url.query).get("title", [""])[0]
    return unquote(path_page)


class LiquidpediaClient:
    headers: ClassVar[dict[str, str]] = {
        **HttpService.headers,
        "User-Agent": "gkfeed-parser/0.1 (https://github.com/gkfeed/parser)",
    }

    def __init__(self, fetch: Callable[[str], Awaitable[bytes]]) -> None:
        self._fetch = fetch

    async def get_page_html(self, page_url: str) -> str:
        try:
            response = json.loads(await self._fetch(self._get_api_url(page_url)))
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as error:
            raise ValueError("Invalid Liquipedia API response") from error

        try:
            html = response["parse"]["text"]
        except (KeyError, TypeError) as error:
            raise ValueError("Unexpected Liquipedia API response") from error

        # MediaWiki's legacy response wraps the rendered HTML in a ``*`` key.
        # Keep accepting that shape for cached responses and older wikis.
        if isinstance(html, dict):
            html = html.get("*")

        if not isinstance(html, str):
            raise ValueError(  # noqa: TRY004 - malformed parser data is a value error
                "Liquipedia API response does not contain HTML"
            )

        return html

    @staticmethod
    def _get_api_url(page_url: str) -> str:
        url = urlsplit(page_url)
        path_parts = url.path.strip("/").split("/", maxsplit=1)
        if len(path_parts) != 2 or not all(path_parts):
            raise ValueError("Invalid Liquipedia page URL")

        wiki, page = path_parts
        page = get_page_title(url, page)
        if not page:
            raise ValueError("Invalid Liquipedia page URL")

        query = urlencode(
            {
                "action": "parse",
                "page": unquote(page),
                "prop": "text",
                "format": "json",
                "formatversion": 2,
            }
        )
        return urlunsplit((url.scheme, url.netloc, f"/{wiki}/api.php", query, ""))
