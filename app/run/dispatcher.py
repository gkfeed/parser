import asyncio
from collections.abc import Awaitable, Callable

import structlog
from asyncpg import InterfaceError, PostgresError
from sqlalchemy.exc import DBAPIError, DisconnectionError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from app.configs.db import engine, session_factory
from app.configs.env import BROKER_URL
from app.core.dispatcher import Dispatcher
from app.services.broker import BrokerService
from app.services.repositories.feed import FeedRepository
from app.services.repositories.feed_parser import FeedParserRepository
from app.services.repositories.item import ItemsRepository
from app.utils.logging import configure_logging

logger = structlog.get_logger(__name__)

CYCLE_PAUSE_SECONDS = 60
DATABASE_RETRY_SECONDS = (1, 2, 5, 10, 30, 60)


async def _dispatch_cycle(dispatcher: Dispatcher) -> bool:
    succeeded = True
    try:
        await dispatcher.dispatch()
    except* (
        DBAPIError,
        DisconnectionError,
        SQLAlchemyTimeoutError,
        PostgresError,
        InterfaceError,
        OSError,
    ):
        # TaskGroup failures can be nested. Unmatched exceptions still propagate.
        succeeded = False
        logger.exception("dispatch_database_failed")
    return succeeded


async def _dispatch_cycles(
    dispatcher: Dispatcher, sleep: Callable[[float], Awaitable[None]]
) -> None:
    retry_index = 0
    while True:
        logger.info("dispatch_cycle_started")
        if await _dispatch_cycle(dispatcher):
            retry_index = 0
            await sleep(CYCLE_PAUSE_SECONDS)
            continue
        delay = DATABASE_RETRY_SECONDS[retry_index]
        retry_index = min(retry_index + 1, len(DATABASE_RETRY_SECONDS) - 1)
        logger.warning("dispatch_database_retry", retry_in_seconds=delay)
        await sleep(delay)


async def dispatch_broker(
    dispatcher: Dispatcher | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    configure_logging()
    if dispatcher is not None:
        await _dispatch_cycles(dispatcher, sleep)
        return
    dispatcher = Dispatcher(
        broker=BrokerService(BROKER_URL),
        feed_parser_repository=FeedParserRepository(session_factory),
        feed_repository=FeedRepository(session_factory),
        items_repository=ItemsRepository(session_factory),
    )
    try:
        await _dispatch_cycles(dispatcher, sleep)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(dispatch_broker())
