# parser
gkfeed parser

## Setup

### Database Migration

To apply database migrations using Alembic, run:

```bash
make migrate
```

This command executes `IS_WORKER=1 .venv/bin/alembic upgrade head`.

## Environment Variables

The application requires several environment variables to be set (typically in a `.env` file).

### Database Configuration

`DB_URL` must use an asynchronous driver.

#### PostgreSQL
You can use either:
- `postgresql+asyncpg://user:password@host:port/dbname`
- `postgres://user:password@host:port/dbname` (automatically converted to `asyncpg`)

#### SQLite
For SQLite, you **must** use `sqlite+aiosqlite:///` followed by the path to the database file (note the three slashes for a relative path):
- `sqlite+aiosqlite:///data/db.sqlite`

*Note: `sqlite://data/db.sqlite` will not work as it lacks the required async driver and correct URI format.*
