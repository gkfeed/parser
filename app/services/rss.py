from bs4 import BeautifulSoup

from app.services.http import HttpService


class RSSParser:
    @staticmethod
    async def parse_feed(url: str) -> list[dict[str, str]]:
        try:
            html = await HttpService.get(url)
            soup = BeautifulSoup(html, "xml")
            items = []
            for item in soup.find_all("item"):
                title_tag = item.find("title")
                link_tag = item.find("link")
                description_tag = item.find("description")
                pub_date_tag = item.find("pubDate")
                guid_tag = item.find("guid")
                items.append(
                    {
                        "title": title_tag.text if title_tag else "",
                        "link": link_tag.text if link_tag else "",
                        "description": description_tag.text if description_tag else "",
                        "pub_date": pub_date_tag.text if pub_date_tag else "",
                        "guid": guid_tag.text if guid_tag else "",
                    }
                )
            return items
        except Exception as e:
            raise ValueError(f"Failed to parse feed: {str(e)}") from e
