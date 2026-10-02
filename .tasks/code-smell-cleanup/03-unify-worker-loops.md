# 03: Unify light and heavy worker loops

**What to build:** Run light and heavy parser workers through one shared loop while preserving their separate entry points and parser assignments.

**Blocked by:** 02: Introduce a ParserId domain type.

**Status:** ready

- [ ] One implementation owns worker loop creation and repeated parser execution.
- [ ] Light and heavy entry points supply only their respective parser identifiers.
- [ ] Shutdown, concurrency, and error behavior remain unchanged.
- [ ] Both worker entry points remain independently runnable.
- [ ] `make lint` and `make test` pass.
