# 06: Type Instagram API responses

**What to build:** Parse Instagram API payloads through explicit response adapters instead of navigating nested untyped dictionaries in feed logic.

**Blocked by:** 05: Unify HTTP request execution.

**Status:** ready

- [ ] Profile and feed payloads are converted into typed application data at the HTTP boundary.
- [ ] Missing or malformed required fields produce a deliberate parse outcome.
- [ ] Rate limiting remains distinguishable from malformed responses and empty feeds.
- [ ] Feed logic no longer depends on the remote JSON nesting structure.
- [ ] Integration-style tests cover valid, malformed, empty, and rate-limited responses.
- [ ] `make lint` and `make test` pass.
