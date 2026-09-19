# 15: Remove unused abstractions

**What to build:** Delete unreferenced browser factories, empty inheritance layers, and generic utility decorators that have no project callers.

**Blocked by:** None (can start immediately).

**Status:** ready

- [ ] Unreachable Firefox driver factories are removed unless a supported browser selection path uses them.
- [ ] The empty cache service inheritance layer is removed.
- [ ] Unused async wrapping, execution timing, and exception-to-empty decorators are removed.
- [ ] No supported import or runtime path references the removed symbols.
- [ ] Dependency imports left unused by the cleanup are removed.
- [ ] `make lint` and `make test` pass.
