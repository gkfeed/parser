def normalize_db_url(url: str) -> str:
    url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    url = url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return url
