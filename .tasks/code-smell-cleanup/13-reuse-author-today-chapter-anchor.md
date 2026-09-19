# 13: Reuse the Author Today chapter anchor

**What to build:** Resolve and validate each Author Today chapter anchor once for title and link extraction.

**Blocked by:** None (can start immediately).

**Status:** ready

- [ ] Title and link extraction use one chapter-anchor operation.
- [ ] Missing anchors, titles, and links retain clear failure behavior.
- [ ] Existing chapter title, URL joining, and publication date behavior remain unchanged.
- [ ] Integration-style tests cover valid and malformed chapter entries.
- [ ] `make lint` and `make test` pass.
