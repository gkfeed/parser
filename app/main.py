import asyncio
import time

from app.settings import DB_URL, MODELS
from app import models
from app.parsers import PARSERS
from app.middlewares import MIDDLEWARES

from app.core.dispatcher import Dispatcher


time.sleep(10)
asyncio.run(models.setup(DB_URL, MODELS))

for parser_type in PARSERS:
    Dispatcher.register_parser(parser_type, PARSERS[parser_type])

for middleware in MIDDLEWARES:
    Dispatcher.register_middleware(middleware)

asyncio.run(Dispatcher.start_polling())
