import os

from dotenv import load_dotenv


load_dotenv()

try:
    DB_URL = os.environ["DB_URL"]
    TWITCH_CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
    TWITCH_CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]
    REDIS_HOST = os.environ["REDIS_HOST"]
    IS_WORKER = bool(int(os.environ["IS_WORKER"]))
except ValueError:
    raise ValueError("Missing configuration")

SELENIUM_COOKIES_PATH = "/data/cookies.pkl"


MODELS = [
    "app.models.feed",
    "app.models.item",
]
