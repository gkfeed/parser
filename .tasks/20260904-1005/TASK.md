# P05: Commit parser results atomically

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [P02](../20260904-1002/TASK.md), [P03](../20260904-1003/TASK.md)

## Goal

Prevent a database failure from committing a hash without its item or parser
state.

## Plan

- [ ] Add one parser-owned persistence operation with one `AsyncSession` and
      one transaction.
- [ ] Keep broker I/O outside the transaction.
- [ ] Check that the feed still exists before writing.
- [ ] Deduplicate and write items and hashes in the same transaction.
- [ ] Upsert `feed_parser` with PostgreSQL `ON CONFLICT` in that transaction.
- [ ] Treat a deleted feed as a successfully discarded result.
- [ ] Do not compare changed feed URL or type with the broker request.
- [ ] Test rollback and safe retry through public behavior.
- [ ] Run `make lint` and `make test`.

## Definition of done

Items, hashes, and parser state commit together or all roll back.
