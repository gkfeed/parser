# parser
gkfeed parser

## Setup

### Database schema

[`gkfeed/infra`](https://github.com/gkfeed/infra) owns and prepares the PostgreSQL
schema. An operator must apply its migrations before deploying the parser,
following the [infra migration policy](https://github.com/gkfeed/infra/blob/master/docs/migrations.md).
The parser has no schema migration commands and does not execute DDL.

With the application environment configured, check schema compatibility before
starting the parser:

```bash
.venv/bin/python -m app.run.check_schema_compatibility
```

This read-only check queries `public.schema_migrations` for the parser's minimum
migration ID, currently `20260904184133`, or a later ID. It accepts later
compatible migrations and exits with status 1 if the registry is missing,
unreadable, or too old. It never applies migrations or repairs the schema.
Use a database identity with the `gkfeed_parser` role provisioned by infra.

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

- `worker_light` handles one light-parser task at a time in each container.
  Run more light containers to process tasks concurrently.
- `worker_http` handles the HTTP parsers formerly assigned to heavy, one task
  at a time.
- `worker_browser` handles Selenium parsers, one task at a time, and owns one
  Grid slot.

Each worker runs in its own container. Feed types and broker function names are
unchanged. Multiple light containers can process feeds of the same parser type.

For example, run three light containers locally:

```bash
docker compose up -d --scale worker_light=3 worker_light
```

Use the production overlay when scaling on the server:

```bash
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d --scale worker_light=3 worker_light
```

To skip parser types in all workers, add them to `ignored_parser_types`:

```python
ignored_parser_types = {Parser.YT, Parser.REZKA_COLLECTION}
```

## Docker worker logs

Docker workers append their stdout and stderr to persistent text files:

- `~/.local/share/gkfeed/logs/worker_light.txt`
- `~/.local/share/gkfeed/logs/worker_http.txt`
- `~/.local/share/gkfeed/logs/worker_browser.txt`

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
their image digests. The browser services are opt-in through the `browser`
profile in both Compose files. Normal server deployments do not start or pull
the browser.

Remote Selenium commands do not retry transport failures. Session cleanup waits
up to 10 seconds for `quit()`. If it fails, the browser worker requests recovery
through the shared `selenium_recovery` volume and waits up to 30 seconds for Grid
readiness. Chrome's watchdog restarts the container if the failed session still
occupies a slot, or Grid is unreachable. It ignores requests for sessions that
have already ended. This does not require access to the Docker socket.

Cleanup and recovery emit `selenium_quit_failed`, `selenium_grid_recovered`,
`selenium_grid_recovery_failed`, and `selenium_grid_restart_requested` events with
the session ID. Stories blocks `player.avplayer.com` before loading the page as
a temporary workaround for the advertising iframe hang.

`make docker-update` pulls the current branch, recreates the Compose project,
and starts the dispatcher, light worker, HTTP worker, and Redis. The browser worker
and Chrome belong to the optional `browser` profile and are excluded from a normal
deployment.

Start or stop the browser worker and Chrome locally with:

```bash
make docker-browser-start
make docker-browser-stop
```

Before switching an existing installation, stop its old `worker_light` and
`worker_heavy` containers. Do not run the old heavy worker alongside the new
browser worker: both would try to own the same Grid. `make docker-update` removes
orphaned containers from the old configuration. On the local host, use
`docker compose up -d --remove-orphans worker_light worker_http` after stopping
the old workers, then `make docker-browser-start` if browser processing is needed.

### Database configuration

`DB_URL` must point to PostgreSQL. The parser normalizes the standard PostgreSQL
schemes to use the asyncpg driver.

Accepted formats:

- `postgres://user:password@host:port/dbname`
- `postgresql://user:password@host:port/dbname`
- `postgresql+asyncpg://user:password@host:port/dbname`

SQLite URLs are rejected.
