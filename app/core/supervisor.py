import asyncio

from app.serializers.feed import Feed
from app.services.repositories.feed import FeedRepository
from app.services.repositories.item import ItemsRepository
from app.parsers import FeedParser


class FeedsSupervisor:
    @classmethod
    def on_startup(cls):
        asyncio.run(cls.dispatcher())

    @classmethod
    async def dispatcher(cls):
        try:
            while True:
                print("START FETCHING FEEDS")
                await cls.__fetch_all_feeds()
                await asyncio.sleep(60)
        except Exception as e:
            print("DISPATCHER FAILED WITH ", e)
            import traceback

            traceback.print_exc()
            # await cls.dispatcher()

    @classmethod
    async def __fetch_all_feeds(cls):
        feeds = await FeedRepository.get_all()
        feeds = [
            Feed(
                id=1,
                title="a",
                url="https://www.tiktok.com/sendependa_dio",
                type="tiktok",
            ),
        ]

        async with asyncio.TaskGroup() as tg:
            for feed in feeds:
                if feed.type not in ("twitch",):
                    tg.create_task(cls.__fetch_feed(feed))

    @classmethod
    async def __fetch_feed(cls, feed: Feed):
        items = await FeedParser(feed).parse()
        await ItemsRepository(feed).add_items_to_feed(items)
        if len(items) == 0:
            print("Feed failed: ", feed.url, len(items))
