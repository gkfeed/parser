from bs4 import BeautifulSoup, Tag
from app.services.http import HttpService


class RSSParser:
    @staticmethod
    async def parse_feed(url: str) -> list[dict[str, str]]:
        try:
            html = await HttpService.get(url)
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
