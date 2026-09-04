# P11: Verify the parser PostgreSQL migration

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [P01](../20260904-1001/TASK.md), [P02](../20260904-1002/TASK.md), [P03](../20260904-1003/TASK.md), [P04](../20260904-1004/TASK.md), [P05](../20260904-1005/TASK.md), [P06](../20260904-1006/TASK.md), [P07](../20260904-1007/TASK.md), [P08](../20260904-1008/TASK.md), [P09](../20260904-1009/TASK.md), [P10](../20260904-1010/TASK.md)

## Goal

Check the finished parser work against the agreed contract without adding new
features.

## Plan

- [ ] Search for remaining SQLite and Alembic runtime paths.
- [ ] Confirm eligibility uses one query.
- [ ] Confirm hash, item, and parser state share one transaction.
- [ ] Confirm parser runs no DDL.
- [ ] Confirm README points to `gkfeed/infra`.
- [ ] Fix only defects that contradict completed tasks.
- [ ] Run `make lint` and `make test`.

## Definition of done

Parser uses the external PostgreSQL contract, all checks pass, and the review
finds no remaining work from P01 through P10.
