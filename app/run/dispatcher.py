import asyncio

import structlog

from app.configs.db import engine, session_factory
from app.configs.env import BROKER_URL
from app.core.dispatcher import Dispatcher
from app.services.broker import BrokerService
from app.services.http import HttpService
from app.services.repositories.feed import FeedRepository
from app.services.repositories.feed_parser import FeedParserRepository
from app.services.repositories.item import ItemsRepository
from app.utils.logging import configure_logging

logger = structlog.get_logger(__name__)

CYCLE_PAUSE_SECONDS = 60


async def dispatch_broker():
    configure_logging()
    try:
        async with HttpService():
            await _dispatch_cycles()
    finally:
        await engine.dispose()


async def _dispatch_cycles():
    dispatcher = Dispatcher(
        broker=BrokerService(BROKER_URL),
        feed_parser_repository=FeedParserRepository(session_factory),
        feed_repository=FeedRepository(session_factory),
        items_repository=ItemsRepository(session_factory),
    )
    while True:
        logger.info("dispatch_cycle_started")
        await dispatcher.dispatch()
        await asyncio.sleep(CYCLE_PAUSE_SECONDS)


if __name__ == "__main__":
    asyncio.run(dispatch_broker())
