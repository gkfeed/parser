import asyncio
import time

from app.settings import DB_URL, MODELS, IS_WORKER
from app import models
from app.parsers import PARSERS
from app.middlewares import MIDDLEWARES

from app.core.dispatcher import Dispatcher


if not IS_WORKER:
    time.sleep(10)
asyncio.run(models.setup(DB_URL, MODELS))

dp = Dispatcher()

for parser_type in PARSERS:
    dp.register_parser(parser_type, PARSERS[parser_type])

for middleware in MIDDLEWARES:
    dp.register_middleware(middleware)

asyncio.run(dp.start_polling())
