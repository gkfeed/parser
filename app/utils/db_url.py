from sqlalchemy.engine import URL, make_url


def build_postgres_asyncpg_url(url: str) -> URL:
    parsed_url = make_url(url)
    if parsed_url.drivername not in {
        "postgres",
        "postgresql",
        "postgresql+asyncpg",
    }:
        raise ValueError("DB_URL must use PostgreSQL with the asyncpg driver")

    return parsed_url.set(drivername="postgresql+asyncpg")
