# Task: Add durable Instagram video support

- STATUS: IDEA
- PRIORITY: 3

## Objective

Support videos in the AnonyIG-backed Instagram parser without storing temporary
media URLs that expire and leave broken feed items.

## Background

`InstagramFeed` currently skips media marked as video because the `.mp4` links
returned by AnonyIG expire. Returning those links directly would make stored
items unusable after expiration. URL tokens may also change between fetches,
causing the same post to receive different hashes and appear more than once.

## Plan

### 1. Choose a durable media strategy

- [ ] Determine how long AnonyIG video URLs remain valid.
- [ ] Decide whether to download and store videos, proxy them through durable
      storage, or represent videos with a stable Instagram post link and
      thumbnail.
- [ ] Keep skipping videos if no durable strategy is available.

### 2. Stable post identity

- [ ] Extract a stable post identifier or canonical post URL when available.
- [ ] Generate item hashes from stable post identity or media content rather
      than the temporary video URL and its query parameters.
- [ ] Verify that repeated fetches do not create duplicate items when the media
      URL changes.

### 3. Safe item generation

- [ ] Accept only expected HTTP(S) media URLs and validate their structure.
- [ ] Escape URLs before inserting them into generated HTML attributes.
- [ ] Remove temporary warnings and commented-out implementations once the
      chosen behavior is implemented.
- [ ] Handle video entries that do not contain an image thumbnail.

### 4. Tests

- [ ] Add fixture-based unit tests for valid video entries, missing or malformed
      links, unsafe URLs, and HTML escaping.
- [ ] Test stable hashing across different temporary URLs for the same post.
- [ ] Test the selected behavior after the source media URL expires.
- [ ] Avoid relying on a particular public Instagram account for coverage of
      video parsing behavior.
- [ ] Run `make lint` and `make test`.

## Completion Criteria

- Video items remain useful after AnonyIG's original media URL expires, or the
  parser explicitly continues to skip them.
- The same Instagram post is deduplicated across repeated fetches.
- Untrusted media attributes cannot inject markup into feed item HTML.
- The behavior is covered by deterministic tests.
