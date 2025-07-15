from .db import setup as db_setup

ON_STARTUP = [
    db_setup(),
]
