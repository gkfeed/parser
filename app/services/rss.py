from bs4 import BeautifulSoup, Tag

from app.services.http import HttpClient


class RSSParser:
    @staticmethod
    async def parse_feed(
        url: str, *, http: HttpClient | None = None
    ) -> list[dict[str, str]]:
        try:
            if http is None:
                async with HttpClient() as owned_http:
                    return await RSSParser.parse_feed(url, http=owned_http)

            html = (await http.request_bytes("GET", url)).data
            soup = BeautifulSoup(html, "xml")
            items = []

            for item in soup.find_all("item"):
                if not isinstance(item, Tag):
                    continue

                items.append(
                    {
                        "title": getattr(item.find("title"), "text", ""),
                        "link": getattr(item.find("link"), "text", ""),
                        "description": getattr(item.find("description"), "text", ""),
                        "pub_date": getattr(item.find("pubDate"), "text", ""),
                        "guid": getattr(item.find("guid"), "text", ""),
                    }
                )
            return items

        except Exception as e:
            raise RuntimeError(f"Failed to parse RSS feed '{url}': {e}") from e
