from datetime import timedelta

from app.serializers.feed import Item
from app.services.cache.temporary import \
    TemporaryCacheService, ExpiredCache, UndefinedCache
from app.services.cache.storage.memory import MemoryStorage
from app.services.twitch import Twitch
from app.services.twitch.types import Stream
from ._base import BaseFeed as _BaseFeed


class TwitchFeed(_BaseFeed):
    __cache: TemporaryCacheService[list[Item]] =\
        TemporaryCacheService(MemoryStorage())

    @property
    async def items(self) -> list[Item]:
        try:
            items = self.__cache.get(self.feed.url)
        except (ExpiredCache, UndefinedCache):
            if stream := await Twitch.get_stream(self._streamer_name):
                items = [self._get_stream_item(stream)]
                self.__cache.set(self.feed.url, items, timedelta(hours=1))
            else:
                items = []
        return items

    def _get_stream_item(self, stream: Stream) -> Item:
        return Item(
            title=stream.channel_name + ': ' + stream.title,
            text=stream.title,
            date=stream.started_at,
            link=self.feed.url
        )

    @property
    def _streamer_name(self) -> str:
        return self.feed.url.split('/')[-1]
