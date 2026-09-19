# 11: Remove storage middlemen

**What to build:** Give the dispatcher explicit repository dependencies instead of inheriting stateless classes that only forward calls.

**Blocked by:** None (can start immediately).

**Status:** ready

- [ ] The dispatcher does not inherit storage forwarding classes.
- [ ] Feed selection, item persistence, and scheduling repositories are explicit dependencies.
- [ ] Default runtime wiring retains current repository behavior.
- [ ] Dispatcher tests replace dependencies through public construction rather than method patching.
- [ ] `make lint` and `make test` pass.
