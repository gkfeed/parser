import asyncio
import time

from app.configs.env import IS_WORKER
from app.configs.on_startup import ON_STARTUP
from app.parsers import PARSERS
from app.middlewares import MIDDLEWARES

from app.core.dispatcher import Dispatcher


async def main():
    if not IS_WORKER:
        time.sleep(10)

    dp = Dispatcher()

    for task in ON_STARTUP:
        dp.add_task_on_startup(task)

    for parser_type in PARSERS:
        dp.register_parser(parser_type, PARSERS[parser_type])

    for middleware in MIDDLEWARES:
        dp.register_middleware(middleware)

    await dp.on_startup()
    await dp.start_polling()


if __name__ == "__main__":
    asyncio.run(main())
