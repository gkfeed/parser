# P20: Retry AniLibria mirrors after JSON error responses

- STATUS: PENDING
- PRIORITY: 2
- DEPENDS: none

## Goal

Try the next AniLibria API mirror when a response cannot produce valid release
items, including when the response is valid JSON.

## Reproduction from the 2026-09-14 review

[AnilibriaFeed](../../app/parsers/anilibria.py) accepts any JSON object inside
its mirror retry loop. It validates the release name and episodes afterward,
outside the exception handler that advances to the next mirror.

Make the first mirror return
`{"message":"Service temporarily unavailable"}` and the second return a release
with `name.main` and a valid episode. Reading `AnilibriaFeed.items` raises
`ValueError: Could not extract name.main`; the working mirror is never tried.

## Plan

- [ ] Validate the release fields needed to build items before accepting a
      mirror response, and keep validation failures within the retry path.
- [ ] Continue to another mirror for JSON error objects and malformed release
      data, as well as transport failures and invalid JSON.
- [ ] Preserve a valid release with an empty episode list as a successful empty
      result.
- [ ] Raise a useful error with the underlying cause when every mirror fails.
- [ ] Test `AnilibriaFeed.items` with fixed responses for JSON errors, malformed
      releases, a successful fallback, an empty release, and exhaustion of all
      mirrors. Assert returned items or errors without depending on private
      helper calls or live API availability.
- [ ] Run `make lint` and `make test`.

## Definition of done

A JSON error from an earlier mirror does not prevent a later valid mirror from
producing feed items. Invalid responses cannot escape validation before the
remaining mirrors have been tried.
