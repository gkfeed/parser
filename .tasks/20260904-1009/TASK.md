# P09: Remove Alembic from parser

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [P01](../20260904-1001/TASK.md), [P02](../20260904-1002/TASK.md), external infra migration chain is working

## Goal

Remove schema ownership from parser.

## Plan

- [ ] Delete `alembic/` and `alembic.ini`.
- [ ] Remove the Alembic dependency and Makefile targets.
- [ ] Remove documentation that tells operators to migrate from parser.
- [ ] Document that `gkfeed/infra` prepares the schema.
- [ ] Document that parser only checks its minimum migration ID.
- [ ] Update generated dependency files with project commands.
- [ ] Run `make lint` and `make test`.

## Definition of done

Parser has no command, dependency, or runtime path that changes the database
schema.
