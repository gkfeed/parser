import re
from datetime import datetime, timedelta
from html import escape
from typing import override
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString

from app.core.worker_kind import WorkerKind
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.exceptions import FeedUnavailable
from app.extensions.parsers.hash import ItemLinkHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.serializers.feed import Item
from app.services.http import HttpRequestError, HttpService


class TelegramFeed(ItemLinkHashExtension, HttpParserExtension, CacheFeedExtension):
    worker_kind = WorkerKind.LIGHT
    _cache_storage_time = timedelta(hours=1)

    def _username(self) -> str:
        url = urlsplit(self.feed.url)
        parts = url.path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "s":
            parts = parts[1:]
        if (
            url.scheme not in {"http", "https"}
            or url.netloc.lower() not in {"t.me", "www.t.me"}
            or len(parts) != 1
            or not re.fullmatch(r"[A-Za-z0-9_]{5,32}", parts[0])
            or url.query
            or url.fragment
        ):
            raise FeedUnavailable(self.feed.url, "invalid_telegram_url")
        return parts[0].lower()

    @override
    async def _parse_items(self) -> list[Item]:
        username = self._username()
        try:
            response = await HttpService.get_response(f"https://t.me/s/{username}")
        except HttpRequestError as exc:
            raise FeedUnavailable(self.feed.url, "http_request_failed") from exc
        if response.status != 200:
            raise FeedUnavailable(self.feed.url, f"http_status_{response.status}")
        soup = BeautifulSoup(response.content, "html.parser")
        posts = soup.select(".tgme_widget_message[data-post]")
        if not posts:
            raise FeedUnavailable(self.feed.url, "telegram_preview_unavailable")
        return [self._post_to_item(post, username) for post in posts]

    def _post_to_item(self, post: Tag, username: str) -> Item:
        post_id = str(post.get("data-post", ""))
        if not re.fullmatch(rf"{re.escape(username)}/[0-9]+", post_id, re.IGNORECASE):
            raise FeedUnavailable(self.feed.url, "invalid_telegram_post")
        date_tag = post.select_one("time[datetime]")
        if date_tag is None:
            raise FeedUnavailable(self.feed.url, "missing_telegram_date")
        try:
            date = datetime.fromisoformat(str(date_tag["datetime"]))
            if date.tzinfo is None:
                raise ValueError("missing timezone")
        except ValueError as exc:
            raise FeedUnavailable(self.feed.url, "invalid_telegram_date") from exc
        link = f"https://t.me/{username}/{post_id.split('/')[1]}"
        text_tag = post.select_one(".tgme_widget_message_text")
        title_soup = BeautifulSoup(str(text_tag), "html.parser") if text_tag else None
        if title_soup:
            for br in title_soup.select("br"):
                br.replace_with(NavigableString("\n"))
        plain = title_soup.get_text().strip() if title_soup else ""
        title = next((line for line in plain.splitlines() if line.strip()), "")[:200]
        title = title or f"Telegram: {username}"
        body = self._safe_text(text_tag) if text_tag else ""
        images = []
        for photo in post.select(".tgme_widget_message_photo_wrap[style]"):
            match = re.search(
                r"background-image:\s*url\(['\"]?(https://[^'\")]+)",
                str(photo.get("style", "")),
            )
            if match:
                images.append(f'<img src="{escape(match.group(1), quote=True)}"/>')
        if images:
            body = "<br/>".join([part for part in [body, *images] if part])
        if post.select_one(
            ".tgme_widget_message_video_player, .tgme_widget_message_video_wrap, .tgme_widget_message_document_wrap"
        ) or "roundvideo_media" in (post.get_attribute_list("class")):
            body += f'<br/><a href="{link}">Открыть медиа в Telegram</a>'
        return Item(title=title, text=body, date=date, link=link, guid=link)

    @staticmethod
    def _safe_text(text_tag: Tag) -> str:
        soup = BeautifulSoup(str(text_tag), "html.parser")
        for tag in list(soup.find_all(True)):
            if not isinstance(tag, Tag):
                continue
            if tag.name not in {
                "div",
                "br",
                "a",
                "b",
                "strong",
                "i",
                "em",
                "s",
                "u",
                "code",
                "pre",
            }:
                tag.unwrap()
                continue
            href = tag.get("href") if tag.name == "a" else None
            tag.attrs = {}
            if isinstance(href, str) and urlsplit(href).scheme in {"http", "https"}:
                tag["href"] = href
        root = soup.find("div")
        return root.decode_contents() if isinstance(root, Tag) else ""
