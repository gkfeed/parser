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
CYCLE_RETRY_SECONDS = (1, 2, 5, 10, 30, 60)


async def _dispatch_cycles(dispatcher: Dispatcher) -> None:
    retry_index = 0
    while True:
        logger.info("dispatch_cycle_started")
        try:
            await dispatcher.dispatch()
        except Exception:
            delay = CYCLE_RETRY_SECONDS[retry_index]
            retry_index = min(retry_index + 1, len(CYCLE_RETRY_SECONDS) - 1)
            logger.exception("dispatch_cycle_failed", retry_in_seconds=delay)
            await asyncio.sleep(delay)
            continue
        retry_index = 0
        await asyncio.sleep(CYCLE_PAUSE_SECONDS)


async def dispatch_broker() -> None:
    configure_logging()
    dispatcher = Dispatcher(
        broker=BrokerService(BROKER_URL),
        feed_parser_repository=FeedParserRepository(session_factory),
        feed_repository=FeedRepository(session_factory),
        items_repository=ItemsRepository(session_factory),
    )
    try:
        async with HttpService.connection_pool():
            await _dispatch_cycles(dispatcher)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(dispatch_broker())
