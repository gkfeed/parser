# 04: Encapsulate parser scheduling policy

**What to build:** Give parser configuration a public scheduling policy and make the stored timestamp clearly represent the next time a feed may run.

**Blocked by:** None (can start immediately).

**Status:** ready

- [ ] The dispatcher does not read private cache or scheduling attributes from parser classes.
- [ ] Empty and successful parser results obtain their next delay through one public policy.
- [ ] The model and repository API name the absolute timestamp unambiguously.
- [ ] The existing database column remains compatible without a destructive migration.
- [ ] Failure backoff behavior remains unchanged.
- [ ] `make lint` and `make test` pass.
