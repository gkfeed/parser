# 08: Centralize Instagram MIME detection

**What to build:** Use one media signature detector for Instagram image payloads.

**Blocked by:** None (can start immediately).

**Status:** ready

- [ ] Both Instagram parser implementations use one detector.
- [ ] JPEG, PNG, GIF, and WEBP signatures retain their current MIME results.
- [ ] The fallback behavior for unknown signatures is explicit and covered by tests.
- [ ] No parser contains a copied media-signature cascade.
- [ ] `make lint` and `make test` pass.
