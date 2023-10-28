import asyncio

from app.settings import DB_URL, MODELS
from app import models
from app.core.supervisor import FeedsSupervisor


asyncio.run(models.setup(DB_URL, MODELS))
asyncio.run(FeedsSupervisor.dispatcher())
