# P10: Remove SQLite deployment settings

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [P08](../20260904-1008/TASK.md), [P09](../20260904-1009/TASK.md)

## Goal

Make parser deployment use the externally managed PostgreSQL contract.

## Plan

- [ ] Remove SQLite data mounts from dispatcher and worker services.
- [ ] Document the PostgreSQL `DB_URL` format.
- [ ] Document the parser database role.
- [ ] Document the manual order: migrate infra, then start parser.
- [ ] Do not add a PostgreSQL service to parser compose.
- [ ] Do not commit secrets or login-role setup.
- [ ] Preserve unrelated compose changes already in the worktree.
- [ ] Run `make lint` and `make test`.

## Definition of done

Parser deployment has no `/data/db.sqlite` path and cannot create its schema.
