# P02: Align ORM models with the infra contract

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [P01](../20260904-1001/TASK.md), external infra task I04

## Goal

Make parser's SQLAlchemy mappings match the schema owned by `gkfeed/infra`.

## Plan

- [ ] Compare the current models with `infra/contracts/parser.md` and the
      canonical SQL migration.
- [ ] Keep `INTEGER` primary keys.
- [ ] Map the `item.feed_id` foreign key.
- [ ] Map cascading foreign keys for `feed_parser` and `item_hash`.
- [ ] Map `UNIQUE(feed_id, hash)`.
- [ ] Match nullability and timestamp types.
- [ ] Do not create or generate migrations.
- [ ] Run `make lint` and `make test`.

## Definition of done

SQLAlchemy maps the external schema without owning or modifying it.
