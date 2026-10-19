from datetime import timedelta
from typing import ClassVar, override
from urllib.parse import urlsplit

from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.hash import ItemIdentityHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.serializers.feed import Item
from app.services.mangalib import MangaLibChapter, MangaLibClient


class MangaLibFeed(ItemIdentityHashExtension, HttpParserExtension, CacheFeedExtension):
    _headers: ClassVar[dict[str, str]] = MangaLibClient.headers
    _cache_storage_time = timedelta(hours=1)
    _max_posts = 5

    @override
    async def _parse_items(self) -> list[Item]:
        chapters = await MangaLibClient(self.get_html).get_chapters(
            self._get_slug(), self._max_posts
        )
        return [self._chapter_to_item(chapter) for chapter in chapters]

    def _chapter_to_item(self, chapter: MangaLibChapter) -> Item:
        title = f"Том {chapter.volume}, Глава {chapter.number}"
        if chapter.name:
            title += f" — {chapter.name}"

        return Item(
            title=title,
            text=title,
            date=chapter.created_at,
            link=(
                f"{self._site_base_url()}/ru/{self._get_slug()}"
                f"/read/v{chapter.volume}/c{chapter.number}"
            ),
        )

    def _get_slug(self) -> str:
        parts = [part for part in urlsplit(self.feed.url).path.split("/") if part]
        if "manga" in parts:
            manga_index = parts.index("manga")
            if manga_index + 1 < len(parts):
                return parts[manga_index + 1]
        raise ValueError(f"Could not extract manga slug from URL: {self.feed.url}")

    def _site_base_url(self) -> str:
        parsed_url = urlsplit(self.feed.url)
        return f"{parsed_url.scheme}://{parsed_url.netloc}"
