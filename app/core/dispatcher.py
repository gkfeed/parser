import asyncio
import random

from app.serializers.feed import Feed
from .storage import ItemsStorage, FeedStorage
from .middlewares import MiddlewaresWrapper
from .parsers import FeedParsingContext


class Dispatcher(MiddlewaresWrapper, FeedParsingContext, FeedStorage, ItemsStorage):
    def __init__(self):
        super().__init__()
        super(MiddlewaresWrapper, self).__init__()

    async def start_polling(self):
        print("Start polling")
        feeds = await self._get_all_feeds()
        random.shuffle(feeds)

        async with asyncio.TaskGroup() as tg:
            for feed in feeds:
                tg.create_task(self._fetch_feed(feed))

        await asyncio.sleep(60)
        await self.start_polling()

    async def _fetch_feed(self, feed: Feed):
        data = self.get_parser_initial_data(feed)
        parse_feed = self._wrap_middlewares(self.execute_parser)
        items = await parse_feed(feed, data)
        await self._save_items(feed, items)
