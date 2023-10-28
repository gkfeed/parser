import asyncio

from app.settings import DB_URL, MODELS
from app import models
from app.core.supervisor import FeedsSupervisor


import time

time.sleep(10)
asyncio.run(models.setup(DB_URL, MODELS))
asyncio.run(FeedsSupervisor.dispatcher())
