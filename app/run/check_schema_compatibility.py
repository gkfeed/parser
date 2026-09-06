import asyncio

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.configs.db import engine

PARSER_MINIMUM_MIGRATION_ID = "20260904184133"


class SchemaCompatibilityError(RuntimeError):
    """Raised when the database is not ready for this parser version."""


async def check_schema_compatibility(database: AsyncEngine) -> None:
    statement = text(
        """
        SELECT version
        FROM public.schema_migrations
        WHERE version >= :minimum_version
        LIMIT 1
        """
    )

    try:
        async with database.connect() as connection:
            version = await connection.scalar(
                statement,
                {"minimum_version": PARSER_MINIMUM_MIGRATION_ID},
            )
    except SQLAlchemyError as error:
        raise SchemaCompatibilityError(
            "Database schema is not ready. Apply gkfeed/infra migrations first."
        ) from error

    if version is None:
        raise SchemaCompatibilityError(
            "Database schema is not ready. Apply gkfeed/infra migrations first."
        )


async def main() -> int:
    try:
        await check_schema_compatibility(engine)
    except SchemaCompatibilityError as error:
        print(error)
        return 1

    print("Database schema is ready for the parser.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
