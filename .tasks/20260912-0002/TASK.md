# P15: Preserve instants when converting feed dates to UTC

- STATUS: PENDING
- PRIORITY: 2
- DEPENDS: none

## Goal

Convert feed timestamps to UTC without changing the instant they represent.

## Reproduction from the 2026-09-14 review

[convert_datetime](../../app/utils/datetime.py) combines the parsed calendar date
and wall-clock time with UTC, discarding the original timezone offset.

Give [WebFeed](../../app/parsers/web.py) an RSS item with
`<pubDate>Mon, 14 Sep 2026 10:00:00 +0300</pubDate>`. The returned item has
`2026-09-14T10:00:00+00:00`; the correct instant is
`2026-09-14T07:00:00+00:00`. This shifts publication times and feed ordering.

## Plan

- [ ] Parse each input timestamp once.
- [ ] Convert timezone-aware values with `astimezone(UTC)`.
- [ ] Treat timezone-naive values as UTC and document that assumption in code.
- [ ] Keep the current fallback behavior for invalid dates unless callers need a
      separate error policy.
- [ ] Test positive and negative offsets, UTC input, naive input, and invalid
      input through `convert_datetime`.
- [ ] Verify an RSS item with a non-UTC offset through `WebFeed.items` using a
      fixed response and no external requests.
- [ ] Run `make lint` and `make test`.

## Definition of done

`Wed, 09 Sep 2026 12:00:00 +0300` becomes `2026-09-09T09:00:00+00:00`, and
existing valid UTC timestamps keep their value.
