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

Logging is configured with two optional variables:

- `LOG_LEVEL` controls application verbosity and defaults to `INFO`. Supported
  values are `DEBUG`, `INFO`, `WARNING`, `ERROR`, and `CRITICAL`.
- `LOG_FORMAT` controls the output renderer and defaults to `logfmt`. Supported
  values are `logfmt` and `json`.

Invalid values stop the application during startup rather than silently falling
back to a different logging configuration.

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

## Production Docker deployment

Production combines `docker-compose.yml` with
`docker-compose.production.yml`. The production overlay connects the parser to
the external `gkfeed-infra_default` network and uses an ARM64 Chromium image.

`make docker-update` pulls the current branch, recreates the Compose project,
and starts the dispatcher, light worker, and Redis. The heavy worker and Chrome
belong to the optional `heavy` profile and remain stopped during a normal
deployment.

Start or stop the heavy worker and Chrome with:

```bash
make docker-heavy-start
make docker-heavy-stop
```

### Database configuration

`DB_URL` must point to PostgreSQL. The parser normalizes the standard PostgreSQL
schemes to use the asyncpg driver.

Accepted formats:

- `postgres://user:password@host:port/dbname`
- `postgresql://user:password@host:port/dbname`
- `postgresql+asyncpg://user:password@host:port/dbname`

SQLite URLs are rejected.
