# P14: Include event time in fallback item deduplication

- STATUS: PENDING
- PRIORITY: 2
- DEPENDS: [P05](../20260904-1005/TASK.md)

## Goal

Keep distinct events when a parser returns the same title, link, and text with a
different publication time.

## Reproduction from the 2026-09-14 review

[ItemsRepository](../../app/services/repositories/item.py) identifies existing
items by feed, title, link, and text without comparing their dates.
[TwitchFeed](../../app/parsers/twitch.py) uses the channel URL for every broadcast
and does not generate a hash, so different broadcasts with the same title match
that identity.

Return two streams titled `Daily stream` for the same channel, starting at
`2026-09-13T18:00:00+00:00` and `2026-09-14T18:00:00+00:00`. Parse and save each
through the public parser and repository methods. Only the first broadcast is
stored; both should be present.

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
