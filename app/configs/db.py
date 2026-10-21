from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.utils.db_url import build_postgres_asyncpg_url

from .env import DB_URL as ENV_DB_URL

configured_url = make_url(ENV_DB_URL)
if configured_url.drivername in {"sqlite", "sqlite+aiosqlite"}:
    DB_URL = configured_url.set(drivername="sqlite+aiosqlite")
else:
    DB_URL = build_postgres_asyncpg_url(ENV_DB_URL)

engine = create_async_engine(DB_URL)

session_factory = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)
