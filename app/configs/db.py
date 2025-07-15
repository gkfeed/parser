import os

from dotenv import load_dotenv
from tortoise import Tortoise

load_dotenv()
DB_URL = os.environ["DB_URL"]

MODELS = [
    "app.models.feed",
    "app.models.item",
    "app.models.item_hash",
    "app.models.log",
]


async def setup():
    await Tortoise.init(db_url=DB_URL, modules={"models": MODELS})
    await Tortoise.generate_schemas(safe=True)
