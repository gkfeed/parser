import asyncio

from app.core.new_dispatcher import Dispatcher
from app.configs.env import BROKER_URL


async def dispatch_broker():
    dispatcher = Dispatcher(BROKER_URL)
    while 1:
        print("Starting dispatch cycle...")
        await dispatcher.dispatch()


if __name__ == "__main__":
    asyncio.run(dispatch_broker())
