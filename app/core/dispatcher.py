import asyncio
import random

from app.serializers.feed import Feed
from .storage import ItemsStorage, FeedStorage
from .middlewares import MiddlewaresWrapper
from .parsers import ParsersRegistrator


class Dispatcher(MiddlewaresWrapper, ParsersRegistrator, FeedStorage, ItemsStorage):
    @classmethod
    async def start_polling(cls):
        print("Start polling")
        feeds = await cls._get_all_feeds()
        random.shuffle(feeds)

        async with asyncio.TaskGroup() as tg:
            for feed in feeds:
                tg.create_task(cls._fetch_feed(feed))

        await asyncio.sleep(60)
        await cls.start_polling()

    @classmethod
    async def _fetch_feed(cls, feed: Feed):
        parser = cls._parsers[feed.type]
        parse_feed = cls._wrap_middlewares(parser)
        data = parser(feed, {}).data
        items = await parse_feed(feed, data)
        await cls._save_items(feed, items)
