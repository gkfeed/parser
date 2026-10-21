import pytest
from sqlalchemy.engine import make_url

from app.utils.db_url import build_postgres_asyncpg_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "postgres://user:password@database/parser",
            "postgresql+asyncpg://user:password@database/parser",
        ),
        (
            "postgresql://user:password@database/parser",
            "postgresql+asyncpg://user:password@database/parser",
        ),
        (
            "postgresql+asyncpg://user:password@database/parser",
            "postgresql+asyncpg://user:password@database/parser",
        ),
    ],
)
def test_build_postgres_asyncpg_url_uses_asyncpg(url: str, expected: str) -> None:
    assert build_postgres_asyncpg_url(url) == make_url(expected)


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///data/db.sqlite",
        "sqlite+aiosqlite:///data/db.sqlite",
        "postgresql+psycopg://user:password@database/parser",
    ],
)
def test_build_postgres_asyncpg_url_rejects_unsupported_drivers(url: str) -> None:
    with pytest.raises(ValueError, match="must use PostgreSQL with the asyncpg driver"):
        build_postgres_asyncpg_url(url)
