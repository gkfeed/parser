# 09: Compose TikTok RSS reading

**What to build:** Let the TikTok proxy parser consume RSS conversion as a dependency without inheriting the Web feed parser's parsing and hashing behavior.

**Blocked by:** None (can start immediately).

**Status:** ready

- [ ] RSS payload conversion is available independently of the Web feed parser class.
- [ ] The TikTok proxy parser no longer inherits from the Web feed parser.
- [ ] TikTok keeps its own hashing, link normalization, and video extraction behavior.
- [ ] Web feeds retain their existing RSS behavior.
- [ ] Integration-style tests cover both Web and TikTok RSS flows.
- [ ] `make lint` and `make test` pass.
