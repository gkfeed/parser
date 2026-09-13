# P19: Add deterministic coverage for recent parser changes

- STATUS: PENDING
- PRIORITY: 2
- DEPENDS: none

## Goal

Cover the Instagram, Liquipedia, and TikTok parser contracts in the default test
suite without calling live services.

## Plan

- [ ] Test Instagram load-more behavior with a fake driver that adds media after
      the trigger becomes visible.
- [ ] Verify that Instagram stops at the configured media cap and stops when no
      trigger or new media appears.
- [ ] Keep the image-download concurrency test focused on observable request
      overlap and returned items, without asserting a private constant.
- [ ] Test Liquipedia's current `formatversion=2` response and the legacy nested
      text response with fixed API payloads.
- [ ] Test TikTok channel extraction success, yt-dlp failure translation, missing
      entry URLs, and the returned video limit with fixed extractor results.
- [ ] Leave a small live integration smoke test for each parser, but do not make
      default test success depend on public sites or accounts.
- [ ] Run `make lint` and `make test`.

## Definition of done

`make test` detects regressions in the recent Instagram, Liquipedia, and TikTok
changes without network access or assumptions about private implementation.
