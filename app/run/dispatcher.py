import asyncio

from app.configs.env import BROKER_URL
from app.core.dispatcher import Dispatcher
from app.services.broker import BrokerService
from app.services.http import HttpClient


async def dispatch_broker():
    async with HttpClient() as http:
        dispatcher = Dispatcher(broker=BrokerService(BROKER_URL, http))
        while 1:
            print("Starting dispatch cycle...")
            await dispatcher.dispatch()


if __name__ == "__main__":
    asyncio.run(dispatch_broker())
