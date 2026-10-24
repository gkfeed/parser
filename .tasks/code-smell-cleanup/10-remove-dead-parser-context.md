# 10: Remove the dead parser context and data channel

**What to build:** Remove parser infrastructure that exists only for tests and make parser tests exercise the same construction path used at runtime.

**Blocked by:** 04: Encapsulate parser scheduling policy.

**Status:** partial, compatible runtime transition implemented

The worker now uses `create_parser(feed)` and reads the typed `parser.retry_at`
field. Cache intervals remain typed class attributes and hashing remains explicit
`apply_hashes` behavior. Neither extension writes constructor data anymore.

Final removal is blocked by the prohibition on changing existing tests.
`tests/parsers/__init__.py` still imports `FeedParsingContext`; its
`FakeDispatcher` constructs parsers directly through `_parsers` and passes an
empty dictionary. Several existing parser tests also pass `{}` directly.
The compatibility adapter and optional empty constructor argument remain until
those callers can migrate to `create_parser`. Nonempty constructor data raises
instead of silently losing a retry request. Existing tests are unchanged; new
local HTTP boundary scenarios exercise the worker's runtime construction path.

Scheduling policy remains owned by task 04. This transition preserves the TTL
attributes consumed by the current dispatcher rather than duplicating that work.

- [ ] Production code has one parser registry and construction path.
- [ ] Parser constructors no longer accept or mutate an unconsumed generic data dictionary.
- [x] Cache and hashing configuration remains available through typed parser configuration or behavior.
- [ ] Parser tests use the runtime parser path without a test-only production abstraction.
- [x] Existing parser integration scenarios remain covered.
- [x] `make lint` and `make test` pass.
