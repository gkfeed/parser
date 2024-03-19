import asyncio
import random

from app.serializers.feed import Feed
from app.services.repositories.feed import FeedRepository
from app.services.repositories.item import ItemsRepository
from app.middlewares import wrap_middlewares


# BUG: deprecated
class FeedsSupervisor:
    @classmethod
    def on_startup(cls):
        asyncio.run(cls.dispatcher())

    # NOTE: Start polling
    @classmethod
    async def dispatcher(cls):
        try:
            while True:
                print("START FETCHING FEEDS")
                await cls.__fetch_all_feeds()
                await asyncio.sleep(1)
        except Exception as e:
            print("DISPATCHER FAILED WITH ", e)
            import traceback

            traceback.print_exc()
            await cls.dispatcher()

    @classmethod
    async def __fetch_all_feeds(cls):
        feeds = await FeedRepository.get_all()

        random.shuffle(feeds)

        async with asyncio.TaskGroup() as tg:
            for feed in feeds:
                tg.create_task(cls.__fetch_feed(feed))

    @classmethod
    async def __fetch_feed(cls, feed: Feed):
        items = await wrap_middlewares(feed)
        await ItemsRepository(feed).add_items_to_feed(items)
