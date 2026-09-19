# 07: Centralize Selenium click behavior

**What to build:** Provide one reusable Selenium click operation for parser actions that need JavaScript clicking and timeout tolerance.

**Blocked by:** 01: Eliminate duplicate Selenium caching.

**Status:** ready

- [ ] Instagram and Stories parsers use the same click operation.
- [ ] JavaScript click behavior and timeout handling remain unchanged.
- [ ] Parser implementations no longer duplicate WebDriver interaction details.
- [ ] Tests exercise successful clicks and tolerated timeouts through observable behavior.
- [ ] `make lint` and `make test` pass.
