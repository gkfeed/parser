# P14: Include event time in fallback item deduplication

- STATUS: PENDING
- PRIORITY: 2
- DEPENDS: [P05](../20260904-1005/TASK.md)

## Goal

Keep distinct events when a parser returns the same title, link, and text with a
different publication time.

## Plan

- [ ] Define the fallback identity used for items without a parser-generated
      hash.
- [ ] Include the event date in that identity.
- [ ] Keep hash-based deduplication unchanged.
- [ ] Verify that repeated copies of one event are still discarded.
- [ ] Verify that two Twitch streams with matching text and different
      `started_at` values are both stored.
- [ ] Test through repository or dispatcher behavior without asserting private
      implementation details.
- [ ] Run `make lint` and `make test`.

## Definition of done

The parser stores events with different dates separately while repeated copies
of the same event remain deduplicated.
