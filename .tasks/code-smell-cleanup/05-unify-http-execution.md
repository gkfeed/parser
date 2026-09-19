# 05: Unify HTTP request execution

**What to build:** Route byte, JSON, status, and Twitch requests through one consistent HTTP execution path.

**Blocked by:** None (can start immediately).

**Status:** ready

- [ ] Session creation and network exception translation are implemented once.
- [ ] Existing GET, POST, DELETE, JSON, and status callers preserve their response contracts.
- [ ] Equivalent connection failures produce the same domain exception for every HTTP method.
- [ ] Twitch uses the shared JSON request path and no JSON-returning method is named as HTML retrieval.
- [ ] Tests cover byte, JSON, status, and failure responses without depending on private implementation details.
- [ ] `make lint` and `make test` pass.
