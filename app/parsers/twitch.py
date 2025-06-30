from datetime import timedelta

from app.serializers.feed import Item
from app.services.twitch import Twitch
from app.services.twitch.types import Stream
from app.extensions.parsers.base import BaseFeed as _BaseFeed
from app.extensions.parsers.cache import CacheFeedExtension


class TwitchFeed(CacheFeedExtension, _BaseFeed):
    _cache_storage_time_if_success = timedelta(hours=1)

    @property
    async def items(self) -> list[Item]:
        items = []
        if stream := await Twitch.get_stream(self._streamer_name):
            items = [self._get_stream_item(stream)]
        return items

    def _get_stream_item(self, stream: Stream) -> Item:
        return Item(
            title=stream.channel_name + ": " + stream.title,
            text=stream.title,
            date=stream.started_at,
            link=self.feed.url,
        )

    @property
    def _streamer_name(self) -> str:
        return self.feed.url.split("/")[-1]
