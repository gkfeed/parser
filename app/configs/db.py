from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

import app.models  # noqa: F401
from .env import DB_URL


engine = create_async_engine(DB_URL)
session_factory = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)
