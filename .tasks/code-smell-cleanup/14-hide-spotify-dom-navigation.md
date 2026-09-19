# 14: Hide Spotify DOM navigation

**What to build:** Encapsulate locating the Spotify track container so track and artist extraction do not repeat parent traversal.

**Blocked by:** None (can start immediately).

**Status:** ready

- [ ] One operation locates and validates the container for a track element.
- [ ] Track name, artist, link, and identifier extraction use the shared container contract.
- [ ] Parser methods no longer expose repeated parent traversal.
- [ ] Integration-style tests cover expected markup and missing artist or track links.
- [ ] `make lint` and `make test` pass.
