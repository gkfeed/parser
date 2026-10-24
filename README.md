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

To skip parser types in both light and heavy workers, add them to `ignored_parser_types`:

```python
ignored_parser_types = ["yt", "rezka:collection"]
```

The light worker runs one persistent event loop and accepts up to
`LIGHT_WORKER_CONCURRENCY` feed jobs at once. The default is `4`; values below
`1` fail startup. Slots remain occupied until parsing and broker submission
finish. Queues are polled in round-robin order. A complete empty sweep triggers
an idle delay that grows from 0.1 seconds to at most 1 second, and finding a job
resets the delay. Heavy browser work remains sequential.

On SIGTERM or SIGINT, the light worker stops taking new jobs. It waits for an
in-progress claim and every accepted job, including broker submissions, before
exiting. yt-dlp extraction runs in a thread and finishes before its resources
are released. Graceful shutdown has no application deadline, so allow enough
time for slow sources and extraction retries before forcing the process to stop.

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

## HTTP connections and broker result polling

Wrap a persistent async application loop in `async with HttpService():`. Child
tasks inherit its HTTP session. Nested scopes reuse the outer session, and the
owning scope closes it on normal exit, error, or cancellation. Await or cancel
child tasks before leaving the scope. Calls outside a scope still work and close
their temporary session after each request.

The pool allows 100 concurrent connections in total and 10 per host. Pass
`connection_limit` and `per_host_limit` to `HttpService()` to override these bounds.
Cookies are discarded, and authentication and other request headers are supplied
per request. The session has no default authentication. Existing aiohttp timeout
defaults remain unchanged.

The [published broker API at 1cd7dbd](https://github.com/gakawarstone/gkbroker/blob/1cd7dbde74c888053e32abebbaea08615585474a/app/api.py)
offers a single-task result endpoint without batching or long polling. Each job
therefore polls immediately, then waits 1, 2, 4, and at most 5 seconds between
requests. `BrokerService` accepts `poll_initial_interval` and `poll_max_interval`
overrides. Once the maximum interval is reached, a waiting job makes about one
result request per five seconds instead of one per second. Completion detection
can take up to five seconds plus the result request's duration and event-loop
scheduling delay.

Each wait keeps its own monotonic deadline, including time spent reading result
responses. Sleeps stop at that deadline. Expiry uses the last observed status:
an unclaimed job raises `BrokerNoWorker` and retains its retry key; a processing
job sends a cancellation request before raising `BrokerError`. Cancelling the caller stops its
polling but leaves the remote job and retry key available, as before. Terminal
successes and failures clear the retry key. The deadline starts after enqueueing,
and broker cancellation remains a separate HTTP operation during cleanup.
The published broker reports processing tasks as already acknowledged when asked
to cancel them. This client preserves that behavior; a local timeout does not
guarantee that remote execution has stopped.

A local HTTP server comparison against `dev@8ab45a9` produced these results:

- Twelve sequential requests accepted 12 TCP connections before and 1 within an
  HTTP scope after this change.
- Three simultaneous jobs that became ready after 8 seconds made 27 result
  requests over 30 connections before, and 15 result requests over 3 connections
  after. Total requests, including enqueueing, fell from 30 to 18.
- Result detection moved from 8.018 seconds to 12.016 seconds in that run. The
  additional delay is the polling tradeoff, not time added to the job deadline.

`tests/services/test_http_reuse.py` and `tests/services/test_broker_polling.py`
exercise local HTTP boundaries, connection limits and cleanup, cookie/header
isolation, concurrent successful and failed jobs, deadlines, and cancellation.
They run with `make test` and require no external service.
