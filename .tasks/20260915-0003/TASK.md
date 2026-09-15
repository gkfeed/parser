# P23: Batch item deduplication queries

- STATUS: PENDING
- PRIORITY: 2
- DEPENDS: [P02](../20260904-1002/TASK.md), [P03](../20260904-1003/TASK.md), [P05](../20260904-1005/TASK.md), [P14](../20260912-0001/TASK.md)

## Goal

Reduce database round trips when persisting a batch of parsed items.

## Finding from the 2026-09-15 performance review

`app/services/repositories/item.py` performs up to three sequential SELECTs per
new hashed item before inserting it. The parser's checked-in schema does not
declare indexes for these lookups. Production indexes must be checked against
the canonical infra schema before proposing changes.

## Plan

- [ ] Fetch existing scoped hashes and fallback identities in bounded batches.
- [ ] Deduplicate both against stored rows and within the incoming batch.
- [ ] Preserve the identity rules established by P14 and the atomic persistence
      operation established by P05, including rollback and retry behavior.
- [ ] Follow P03's completed legacy-hash migration policy.
- [ ] Inspect query plans against the canonical PostgreSQL schema. Coordinate
      missing lookup indexes with `gkfeed/infra`; do not generate parser-owned
      migrations or duplicate existing indexes.
- [ ] Measure query counts and elapsed time for representative batch sizes and
      feed histories. Record the fixture size and before/after results.
- [ ] Add integration coverage through public persistence behavior for new
      items, repeated items, same-batch duplicates, and rollback. Keep performance
      measurements separate from brittle exact-query-count assertions.
- [ ] Preserve existing tests and their integration scope. Run `make lint` and
      `make test`, plus relevant integration checks.

## Definition of done

Deduplication reads scale with bounded batches instead of individual items.
Stored items, returned results, and transaction guarantees retain the agreed
behavior, with measured database round-trip reduction.
