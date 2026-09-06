# P01: Add a temporary schema compatibility script

- STATUS: COMPLETED
- PRIORITY: 1
- DEPENDS: external infra task I04

## Goal

Give operators a one-time check that the shared PostgreSQL schema is ready
before the parser cutover.

## Plan

- [x] Add one constant for parser's minimum migration ID.
- [x] Add one standalone script that reads `public.schema_migrations`.
- [x] Accept the required migration and newer compatible migrations.
- [x] Fail with a short error when the required migration is absent.
- [x] Do not run DDL or apply migrations.
- [x] Run `make lint` and `make test`.

## Definition of done

Operators can run `python -m app.run.check_schema_compatibility` before the
cutover. The script never changes the schema and can be deleted after use.
