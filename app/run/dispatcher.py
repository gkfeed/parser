import asyncio

from app.configs.env import BROKER_URL
from app.core.dispatcher import Dispatcher
from app.services.broker import BrokerService
from app.services.http import HttpClient

CYCLE_PAUSE_SECONDS = 60


async def dispatch_broker():
    async with HttpClient() as http:
        dispatcher = Dispatcher(broker=BrokerService(BROKER_URL, http))
        while True:
            print("Starting dispatch cycle...")
            await dispatcher.dispatch()
            await asyncio.sleep(CYCLE_PAUSE_SECONDS)


if __name__ == "__main__":
    asyncio.run(dispatch_broker())
