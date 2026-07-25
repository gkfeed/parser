# parser
gkfeed parser

## Setup

### Database Migration

To apply database migrations using Alembic, run:

```bash
make migrate
```

This command executes `.venv/bin/alembic upgrade head`.

## Environment Variables

The application requires several environment variables to be set (typically in a `.env` file).

## Worker Parser Configuration

Worker parser types are configured in `app/configs/workers.py`.

To skip parser types in both light and heavy workers, add them to `ignored_parser_types`:

```python
ignored_parser_types = ["yt", "rezka:collection"]
```

## Docker worker logs

Docker workers append their stdout and stderr to persistent text files:

- `~/.local/share/gkfeed/logs/worker_light.txt`
- `~/.local/share/gkfeed/logs/worker_heavy.txt`

The output is also available through `docker compose logs`. Set `WORKER_LOG_DIR`
before starting Docker Compose to store the files in a different directory:

```bash
WORKER_LOG_DIR=/path/to/logs docker compose up -d
```

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
