# P15: Preserve instants when converting feed dates to UTC

- STATUS: PENDING
- PRIORITY: 2
- DEPENDS: none

## Goal

Convert feed timestamps to UTC without changing the instant they represent.

## Plan

- [ ] Parse each input timestamp once.
- [ ] Convert timezone-aware values with `astimezone(UTC)`.
- [ ] Treat timezone-naive values as UTC and document that assumption in code.
- [ ] Keep the current fallback behavior for invalid dates unless callers need a
      separate error policy.
- [ ] Test positive and negative offsets, UTC input, naive input, and invalid
      input through `convert_datetime`.
- [ ] Run `make lint` and `make test`.

## Definition of done

`Wed, 09 Sep 2026 12:00:00 +0300` becomes `2026-09-09T09:00:00+00:00`, and
existing valid UTC timestamps keep their value.
