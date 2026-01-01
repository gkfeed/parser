# Move from tortoise to sqlalchemy

- STATUS: COMPLETED
- PRIORITY: 1

## Objective

Migrate the database layer from Tortoise ORM to SQLAlchemy (Async) with AsyncPG. This involves replacing model definitions, database configuration, and repository logic to use SQLAlchemy's `AsyncSession`.
Utilize the existing `app/utils/inject.py` dependency injection mechanism to manage sessions in repositories, avoiding manual session passing.

## Plan

### 1. Dependencies

- [x] Use `uv remove tortoise-orm` to remove the old ORM.
- [x] Use `uv add "sqlalchemy[asyncio]" alembic asyncpg` to add new dependencies.
- [x] Run `make lock` to update `requirements.txt`.

### 2. Configuration

- [x] Create `app/configs/database.py`: (Note: used app/configs/db.py instead)
  - Define `AsyncEngine` and `async_sessionmaker` (expose as `session_factory` or similar).
  - Define `Base` using `DeclarativeBase` (SQLAlchemy 2.0).
- [x] Update `app/configs/__init__.py`:
  - Update `Data` dataclass to include `db_session`.
  - Import `session_factory` and add it to `Container.setup` call.
- [x] Update `app/configs/on_startup.py`:
  - Remove `Tortoise.init` and `generate_schemas`.
  - Implement table creation (e.g., `await conn.run_sync(Base.metadata.create_all)`) for dev/testing ease, or rely on Alembic.

### 3. Models

Refactor `app/models/` to use SQLAlchemy `Mapped` columns and `DeclarativeBase`.

- [x] `app/models/feed.py`: `Feed` model.
- [x] `app/models/item.py`: `Item` model (Updated to use `DateTime(timezone=True)`).
- [x] `app/models/item_hash.py`: `ItemHash` model.

### 4. Repositories

Refactor `app/services/repositories/` to use `@inject`.

- [x] `app/services/repositories/feed.py`:
  - Apply `@inject({"session_factory": "db_session"})` to methods.
  - Wrap logic in `async with session_factory() as session:` to ensure session closure.
- [x] `app/services/repositories/item.py`:
  - Apply `@inject` to methods (e.g., `get_all`, `add_items_to_feed`).
  - Use `async with session:`.
- [x] `app/services/repositories/item_hash.py`:
  - Apply `@inject` to `contains` and `save`.
  - Use `async with session:`.

### 5. Core Logic & Dispatcher

- [x] Update `app/core/dispatcher.py` and `app/core/storage.py`:
  - Remove all code related to creating or passing `session` objects.
  - Rely on Repositories to handle their own sessions via injection.

### 6. Middlewares

- [x] Update `app/middlewares/hash.py`:
  - Just call `ItemsHashRepository` methods.

### 7. Migrations & Testing

- [x] Initialize Alembic (`alembic init -t async`).
- [x] Configure `alembic.ini` and `env.py` to use `DB_URL` from env.
- [x] Generate initial migration (`alembic revision --autogenerate`).
- [x] Run tests and verify that `make lint` and `make test` pass.

## Post-Migration Fixes

- **PostgreSQL Sequence Sync:** Synchronized sequences (`setval`) for `feed`, `item`, and `item_hash` tables to prevent `UniqueViolationError` during inserts.
- **Timezone Support:** Updated `Item.date` to `DateTime(timezone=True)` to ensure compatibility with `asyncpg` and existing data.
- **Test Suite:** Added `tests/test_db.py` to verify full CRUD and duplicate handling for repositories.