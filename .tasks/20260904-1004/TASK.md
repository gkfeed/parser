# P04: Select eligible feeds in one query

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [P02](../20260904-1002/TASK.md)

## Goal

Remove the per-feed `feed_parser` lookup from each dispatch cycle.

## Plan

- [ ] Replace `get_all` plus per-feed lookups with one SQLAlchemy query.
- [ ] Use a left join from `feed` to `feed_parser`.
- [ ] Return feeds with no schedule or an expired `valid_for`.
- [ ] Filter out unsupported parser types.
- [ ] Order results by `feed.id`.
- [ ] Do not change cycle timing or task scheduling.
- [ ] Test due, future, missing-schedule, and unsupported feeds by behavior.
- [ ] Run `make lint` and `make test`.

## Definition of done

One repository call returns the full ordered set of eligible feeds without an
N+1 query pattern.
