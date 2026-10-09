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

Spotify artist feeds use Playwright Chromium in the heavy worker. After installing
Python dependencies locally, install its browser and system dependencies:

```bash
uv run playwright install --with-deps --only-shell chromium
```

The heavy worker Docker build installs Chromium automatically. Spotify waits for
album links with text before reading the page, with a 30 second timeout. A timeout
fails the fetch so a page that has not rendered cannot replace the cached feed
with an empty result. The existing discography fallback, HTML cache, item cache,
and hashes still apply.

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
the external `gkfeed-infra_default` network and uses the official multi-architecture
Chromium image. Chrome and Chromium are pinned to release `4.48.0-20260905` and
their image digests. `make docker-update` pulls the pinned browser image before
recreating containers.

Remote Selenium commands do not retry transport failures. Session cleanup waits
up to 10 seconds for `quit()`. If it fails, the heavy worker requests recovery
through the shared `selenium_recovery` volume and waits up to 30 seconds for Grid
readiness. Chrome's watchdog restarts the container if the failed session still
occupies a slot, or Grid is unreachable. It ignores requests for sessions that
have already ended. This does not require access to the Docker socket.

Cleanup and recovery emit `selenium_quit_failed`, `selenium_grid_recovered`,
`selenium_grid_recovery_failed`, and `selenium_grid_restart_requested` events with
the session ID. Stories blocks `player.avplayer.com` before loading the page as
a temporary workaround for the advertising iframe hang.

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
