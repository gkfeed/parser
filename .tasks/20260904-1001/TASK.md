# P01: Add the schema compatibility check

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: external infra task I04

## Goal

Stop parser before dispatch when the shared PostgreSQL schema is too old or
missing.

## Plan

- [ ] Add one constant for parser's minimum migration ID.
- [ ] Read `public.schema_migrations` before the first dispatch cycle.
- [ ] Accept the required migration and newer compatible migrations.
- [ ] Fail with a short error when the required migration is absent.
- [ ] Do not run DDL or apply migrations.
- [ ] Test observable compatibility behavior through a storage boundary.
- [ ] Run `make lint` and `make test`.

## Definition of done

Parser starts only when its minimum schema migration is present. It never
changes the schema.
