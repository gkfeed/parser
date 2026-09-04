# P03: Remove lazy migration of global hashes

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [P02](../20260904-1002/TASK.md), external infra importer drops legacy `itemhash`

## Goal

Remove runtime support for SQLite hashes that have no `feed_id`.

## Plan

- [ ] Delete the lazy claim path for rows with `feed_id IS NULL`.
- [ ] Make hash lookup and storage use only `(feed_id, hash)`.
- [ ] Remove tests for global legacy hashes.
- [ ] Keep current scoped-hash behavior.
- [ ] Do not refactor transaction ownership in this task.
- [ ] Run `make lint` and `make test`.

## Definition of done

Parser no longer reads, claims, or writes global hashes.
