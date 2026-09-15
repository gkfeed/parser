# P02: Align ORM models with the infra contract

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [P01](../20260904-1001/TASK.md), external infra task I04

## Goal

Make parser's SQLAlchemy mappings match the schema owned by `gkfeed/infra`.

## Reproduction from the 2026-09-14 review

[ItemHash.feed_id](../../app/models/item_hash.py) declares a foreign key without
an `ondelete` action, while
[FeedRepository.delete_by_id](../../app/services/repositories/feed.py) deletes
only the feed row.

Create the current ORM schema in an in-memory SQLite database with
`PRAGMA foreign_keys=ON`, save a feed and an item with a hash, then delete the
feed through the repository. Deletion raises `IntegrityError` because the hash
still references the feed. Existing repository tests leave foreign-key
enforcement disabled and do not detect this mismatch. Check the canonical infra
schema when resolving it.

## Plan

- [ ] Compare the current models with `infra/contracts/parser.md` and the
      canonical SQL migration.
- [ ] Keep `INTEGER` primary keys.
- [ ] Map the `item.feed_id` foreign key.
- [ ] Map cascading foreign keys for `feed_parser` and `item_hash`.
- [ ] Map `UNIQUE(feed_id, hash)`.
- [ ] Match nullability and timestamp types.
- [ ] Verify feed deletion through the repository with foreign keys enforced,
      including a feed that has items, scoped hashes, and parser state. Assert
      dependent-row behavior against the infra contract.
- [ ] Do not create or generate migrations.
- [ ] Run `make lint` and `make test`.

## Definition of done

SQLAlchemy maps the external schema without owning or modifying it.
