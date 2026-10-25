import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.dispatcher import Dispatcher
from app.extensions.parsers.base import BaseFeed
from app.serializers.feed import Feed
from app.services.broker import BrokerService
from app.services.repositories.feed import FeedRepository
from app.services.repositories.feed_parser import FeedParserRepository
from app.services.repositories.item import ItemsRepository
from app.utils.db_url import build_postgres_asyncpg_url


@dataclass
class PostgresDatabase:
    owner: AsyncEngine
    parser: AsyncEngine

    @property
    def sessions(self) -> async_sessionmaker[AsyncSession]:
        return async_sessionmaker(self.parser, expire_on_commit=False)

    def dispatcher(self, broker: BrokerService) -> Dispatcher:
        return Dispatcher(
            broker=broker,
            feed_repository=FeedRepository(self.sessions),
            feed_parser_repository=FeedParserRepository(self.sessions),
            items_repository=ItemsRepository(self.sessions),
            parsers={"test": BaseFeed},
        )

    async def create_feed(self, title: str, parser_type: str = "test") -> Feed:
        async with self.owner.begin() as connection:
            user_id = await connection.scalar(
                text("INSERT INTO public.users (name) VALUES (:name) RETURNING id"),
                {"name": str(uuid4())},
            )
            feed_id = await connection.scalar(
                text(
                    "INSERT INTO public.feed (title, url, type, user_id) "
                    "VALUES (:title, :url, :type, :user_id) RETURNING id"
                ),
                {
                    "title": title,
                    "url": f"https://example.com/{title}",
                    "type": parser_type,
                    "user_id": user_id,
                },
            )
        return Feed(
            id=feed_id,
            title=title,
            url=f"https://example.com/{title}",
            type=parser_type,
        )


@pytest.fixture
async def postgres_database() -> AsyncGenerator[PostgresDatabase]:
    configured_url = os.environ.get("PARSER_TEST_POSTGRES_URL")
    if not configured_url:
        raise pytest.UsageError(
            "Set PARSER_TEST_POSTGRES_URL to an empty database migrated by gkfeed/infra. "
            "See tests/postgres/README.md."
        )
    template_url = build_postgres_asyncpg_url(configured_url)
    if not template_url.database:
        raise ValueError("PARSER_TEST_POSTGRES_URL must include a database name")

    control = create_async_engine(
        template_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    database_name = f"parser_contract_{uuid4().hex}"
    quote = control.dialect.identifier_preparer.quote_identifier
    try:
        async with control.connect() as connection:
            await connection.execute(
                text(
                    f"CREATE DATABASE {quote(database_name)} "
                    f"TEMPLATE {quote(template_url.database)}"
                )
            )
            # Database ACLs are not copied by CREATE DATABASE ... TEMPLATE.
            await connection.execute(
                text(
                    f"REVOKE CREATE, TEMPORARY ON DATABASE {quote(database_name)} "
                    "FROM PUBLIC"
                )
            )
        async with configured_database(template_url.set(database=database_name)) as db:
            yield db
    finally:
        async with control.connect() as connection:
            await connection.execute(
                text(f"DROP DATABASE IF EXISTS {quote(database_name)} WITH (FORCE)")
            )
        await control.dispose()


@asynccontextmanager
async def configured_database(url: URL) -> AsyncGenerator[PostgresDatabase]:
    owner = create_async_engine(url, poolclass=NullPool)
    parser = create_async_engine(
        url,
        connect_args={"server_settings": {"role": "gkfeed_parser"}},
        poolclass=NullPool,
    )
    try:
        yield PostgresDatabase(owner=owner, parser=parser)
    finally:
        await parser.dispose()
        await owner.dispose()
