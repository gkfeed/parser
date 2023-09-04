import os
# import logging

from dotenv import load_dotenv


load_dotenv()

# logging.basicConfig(format='%(levelname)s: %(asctime)s: %(message)s')

try:
    DB_URL = os.environ['DB_URL']
    TWITCH_CLIENT_ID = os.environ['TWITCH_CLIENT_ID']
    TWITCH_CLIENT_SECRET = os.environ['TWITCH_CLIENT_SECRET']
    REDIS_HOST = os.environ['REDIS_HOST']
except ValueError:
    raise ValueError('Missing configuration')


MODELS = [
    'app.models.feed',
    'app.models.item',
]
