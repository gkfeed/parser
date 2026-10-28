# 06: Type Instagram API responses

**What to build:** Parse Instagram API payloads through explicit response adapters instead of navigating nested untyped dictionaries in feed logic.

**Blocked by:** 05: Unify HTTP request execution.

**Status:** implemented; awaiting HTTP prerequisite 05 before final integration and closure.

- [x] Profile and feed payloads are converted into typed application data at the HTTP boundary.
- [x] Missing or malformed required fields produce a deliberate parse outcome.
- [x] Rate limiting remains distinguishable from malformed responses and empty feeds.
- [x] Feed logic no longer depends on the remote JSON nesting structure.
- [x] Integration-style tests cover valid, malformed, empty, and rate-limited responses.
- [x] `make lint` and `make test` pass.

The adapters and their HTTP contract checks pass on the current `HttpService` interface. Task 05 has no PR yet; reuse its completed branch/PR and rerun these checks before closing this task. The task file is retained until that prerequisite is resolved.
