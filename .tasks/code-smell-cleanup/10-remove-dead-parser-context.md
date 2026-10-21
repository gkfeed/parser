# 10: Remove the dead parser context and data channel

**What to build:** Remove parser infrastructure that exists only for tests and make parser tests exercise the same construction path used at runtime.

**Blocked by:** 04: Encapsulate parser scheduling policy.

**Status:** ready

- [ ] Production code has one parser registry and construction path.
- [ ] Parser constructors no longer accept or mutate an unconsumed generic data dictionary.
- [ ] Cache and hashing configuration remains available through typed parser configuration or behavior.
- [ ] Parser tests use the runtime parser path without a test-only production abstraction.
- [ ] Existing parser integration scenarios remain covered.
- [ ] `make lint` and `make test` pass.
