import os

from dotenv import load_dotenv


load_dotenv()

try:
    # Do not import this value for database setup; use app.configs.db.DB_URL instead.
    DB_URL = os.environ["DB_URL"]
    TWITCH_CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
    TWITCH_CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]
    REDIS_HOST = os.environ["REDIS_HOST"]
    BROKER_URL = os.environ.get("BROKER_URL", "http://127.0.0.1:8000")
    SELENIUM_DOCKER_URL = os.environ.get("SELENIUM_DOCKER_URL", "http://10.5.0.5:4444")
except (ValueError, KeyError):
    raise ValueError("Missing configuration")
