import asyncio
import logging

from app.configs.env import BROKER_URL
from app.core.dispatcher import Dispatcher
from app.services.broker import BrokerService
from app.utils.logging import configure_logging

logger = logging.getLogger(__name__)

CYCLE_PAUSE_SECONDS = 60


async def dispatch_broker():
    configure_logging()
    dispatcher = Dispatcher(broker=BrokerService(BROKER_URL))
    while True:
        logger.info("Starting dispatch cycle")
        await dispatcher.dispatch()
        await asyncio.sleep(CYCLE_PAUSE_SECONDS)


if __name__ == "__main__":
    asyncio.run(dispatch_broker())
