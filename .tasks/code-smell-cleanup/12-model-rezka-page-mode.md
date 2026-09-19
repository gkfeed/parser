# 12: Model the Rezka page mode

**What to build:** Determine whether a Rezka page represents a film or series once and reuse that decision throughout parsing.

**Blocked by:** None (can start immediately).

**Status:** ready

- [ ] Film-versus-series detection has one named representation.
- [ ] Post extraction, title construction, and content validation use the shared page mode.
- [ ] Collection title and text extraction share one validated anchor lookup.
- [ ] Film, series, latest-page fallback, and collection behavior remain covered by integration tests.
- [ ] `make lint` and `make test` pass.
