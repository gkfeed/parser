# Task: Consider per-post parser error handling

- STATUS: IDEA
- PRIORITY: 3

## Objective

Consider adding optional per-post error handling to `PostToItemsMixin` so parsers can skip malformed posts without overriding the whole `items` property.

## Notes

- Current example: `HltvFeed` overrides `items` to preserve per-row parse failure handling.
- Keep this optional; most parsers should continue failing loudly when page structure changes.
- A future design could expose a small hook or class setting for parsers that intentionally skip invalid posts.
