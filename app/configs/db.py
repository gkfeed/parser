from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

import app.models  # noqa: F401
from .env import DB_URL as ENV_DB_URL


DB_URL = ENV_DB_URL.replace("postgres://", "postgresql+asyncpg://")
DB_URL = DB_URL.replace("sqlite://", "sqlite+aiosqlite://")


connect_args = {}
if DB_URL.startswith("sqlite"):
    connect_args["timeout"] = 30

engine = create_async_engine(DB_URL, connect_args=connect_args)


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if DB_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


session_factory = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)
