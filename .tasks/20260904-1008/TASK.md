# P08: Make database configuration PostgreSQL-only

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: external infra importer is ready

## Goal

Remove SQLite runtime support and accept the PostgreSQL URLs used by infra.

## Plan

- [ ] Normalize `postgres://`, `postgresql://`, and
      `postgresql+asyncpg://` to the asyncpg dialect.
- [ ] Reject SQLite URLs with a clear configuration error.
- [ ] Remove SQLite connection arguments and PRAGMA hooks.
- [ ] Remove the `aiosqlite` runtime dependency.
- [ ] Update project lock or generated requirement files with project commands.
- [ ] Do not add `pool_pre_ping`.
- [ ] Test URL normalization and rejection behavior.
- [ ] Run `make lint` and `make test`.

## Definition of done

Parser connects only through asyncpg and contains no SQLite connection code.
