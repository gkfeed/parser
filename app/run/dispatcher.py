import asyncio

from app.configs.db import engine, session_factory
from app.configs.env import BROKER_URL
from app.core.dispatcher import Dispatcher
from app.services.broker import BrokerService
from app.services.repositories.feed import FeedRepository
from app.services.repositories.feed_parser import FeedParserRepository
from app.services.repositories.item import ItemsRepository

CYCLE_PAUSE_SECONDS = 60


async def dispatch_broker():
    dispatcher = Dispatcher(
        broker=BrokerService(BROKER_URL),
        feed_parser_repository=FeedParserRepository(session_factory),
        feed_repository=FeedRepository(session_factory),
        items_repository=ItemsRepository(session_factory),
    )
    try:
        while True:
            print("Starting dispatch cycle...")
            await dispatcher.dispatch()
            await asyncio.sleep(CYCLE_PAUSE_SECONDS)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(dispatch_broker())
