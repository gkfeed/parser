# 01: Eliminate duplicate Selenium caching

**What to build:** Ensure every parser HTML request passes through exactly one cache layer, including parsers that use Selenium.

**Blocked by:** None (can start immediately).

**Status:** ready

- [ ] HTTP and Selenium parser subclasses apply a single cache wrapper to HTML retrieval.
- [ ] A cache miss performs one underlying retrieval and one cache write.
- [ ] A cache hit returns the cached response without calling the underlying client.
- [ ] Existing parser behavior and cache durations remain unchanged.
- [ ] `make lint` and `make test` pass.
