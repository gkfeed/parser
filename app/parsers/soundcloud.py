from typing import override

from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.http import HttpParserExtension
from app.serializers.feed import Item
from app.services.hash import HashService
from app.services.soundcloud import SoundCloudClient


class SoundCloudFeed(ItemsHashExtension, HttpParserExtension):
    @override
    async def _parse_items(self) -> list[Item]:
        tracks = await SoundCloudClient(self.get_html).get_tracks(self.feed.url)
        return [
            Item(
                title=track.title,
                text=track.description,
                date=track.date,
                link=track.url,
                guid=track.id,
            )
            for track in tracks
        ]

    @override
    async def _generate_hash(self, item: Item) -> str:
        if not item.guid:
            raise ValueError("SoundCloud track ID is missing")
        return HashService.hash_str(item.guid)
