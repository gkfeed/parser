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

Set `DB_URL` in the parser's local `.env` to the externally managed PostgreSQL
database. The parser normalizes the standard PostgreSQL schemes to use the
asyncpg driver.

Accepted formats:

- `postgres://user:password@host:port/dbname`
- `postgresql://user:password@host:port/dbname`
- `postgresql+asyncpg://user:password@host:port/dbname`

Use the parser LOGIN identity provisioned by the operator, with inherited
membership in the `gkfeed_parser` NOLOGIN group. The group permits reads of
feeds and the migration registry, inserts of items, and writes of parser state
and item hashes. It does not permit schema creation or migration, feed writes,
or item deletion. The LOGIN identity must own no database objects and have no
extra grants or elevated role attributes. Do not use the migration owner or a
superuser for `DB_URL`. See the infra
[application role contract](https://github.com/gkfeed/infra/blob/master/docs/application-roles.md).

Percent-encode special characters in URL credentials. Keep real connection URLs,
passwords, and LOGIN-role provisioning outside Git. Inside the production
Compose network, use the infra service hostname `postgres` and port `5432`.
`localhost` inside a parser container refers to that container, not the database.

SQLite is only supported by local test fixtures. Deployment must use PostgreSQL;
parser Compose has no database service or SQLite data volume.

### Database deployment order

The operator must migrate infra before starting or updating the parser:

1. In the `gkfeed/infra` checkout, start the managed PostgreSQL service and apply
   merged migrations with the operator's connection configuration:

   ```bash
   make postgres-up
   make status
   make migrate
   make status
   ```

   The final status must show no pending migrations. Infra owns the schema and
   grants; parser deployment must not run DDL. Follow the infra
   [migration policy](https://github.com/gkfeed/infra/blob/master/docs/migrations.md).
2. Ensure the parser LOGIN identity has the role described above, and configure
   the parser's `.env`. The infra Compose project must provide the external
   `gkfeed-infra_default` network used by the production overlay.
3. In the parser checkout, build the images and run the read-only schema check
   with the same environment and network as the dispatcher:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.production.yml build
   docker compose -f docker-compose.yml -f docker-compose.production.yml run --rm --no-deps dispatcher python -m app.run.check_schema_compatibility
   ```

   The check reads `public.schema_migrations` and requires migration
   `20260904184133` or a later ID. It exits unsuccessfully if the registry is
   missing, too old, or inaccessible. Resolve the error in infra before starting
   the parser; the check does not create or migrate the schema.
4. Start the parser only after the check succeeds:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.production.yml up -d
   ```

For subsequent updates, complete the infra migration and schema check before
running `make docker-update`. Enable the optional browser worker afterward with
`make docker-browser-start` on the local host.
