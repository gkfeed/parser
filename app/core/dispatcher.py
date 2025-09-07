import asyncio
import random
from typing import Coroutine

from app.serializers.feed import Feed
from .storage import ItemsStorage, FeedStorage
from .middlewares import MiddlewaresWrapper
from .parsers import FeedParsingContext


class Dispatcher(MiddlewaresWrapper, FeedParsingContext, FeedStorage, ItemsStorage):
    _tasks_on_startup: list[Coroutine] = []
    __queue: list = []

    def __init__(self):
        super().__init__()
        super(MiddlewaresWrapper, self).__init__()

    async def on_startup(self):
        for task in self._tasks_on_startup:
            await task

    def add_task_on_startup(self, task: Coroutine):
        self._tasks_on_startup.append(task)

    async def start_polling(self):
        print("Start polling")

        async with asyncio.TaskGroup() as tg:
            while 1:
                feeds = await self._get_all_feeds()
                random.shuffle(feeds)
                for feed in feeds:
                    if feed not in self.__queue:
                        self.__queue.append(feed)
                        # await self._fetch_feed(feed)
                        tg.create_task(self._fetch_feed(feed))
                        await asyncio.sleep(1)

    async def _fetch_feed(self, feed: Feed):
        data = self.get_parser_initial_data(feed)
        parse_feed = self._wrap_middlewares(self.execute_parser)
        items = await parse_feed(feed, data)
        await self._save_items(feed, items)

        if feed in self.__queue:
            self.__queue.remove(feed)
